"""Operaciones de persistencia y reglas de negocio para reportes.

Las transiciones que modifican varias piezas de estado se ejecutan dentro de
transacciones. Los bloqueos ``FOR UPDATE`` serializan operaciones sobre el
mismo usuario o reporte y complementan el índice parcial que impide tener dos
borradores activos.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from app.models import (
    EventType,
    Report,
    ReportKind,
    ReportStatus,
    WorkflowStep,
)
from app.repositories import Database, acquire_connection, transaction


class ReportRepositoryError(RuntimeError):
    """Error base de las operaciones de reportes."""


class ReportNotFoundError(ReportRepositoryError):
    """El UUID indicado no corresponde a un reporte existente."""


class InvalidReportStateError(ReportRepositoryError):
    """La operación no es válida en el estado actual del reporte."""


class ReportValidationError(ValueError):
    """El borrador no contiene todos los datos requeridos para enviarse."""

    def __init__(self, problems: list[str] | tuple[str, ...]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


def _uuid(value: object) -> UUID:
    """Convierte el tipo UUID de asyncpg conservando type hints precisos."""

    return value if isinstance(value, UUID) else UUID(str(value))


def _report_from_record(row: Mapping[str, Any]) -> Report:
    """Transforma una fila de asyncpg en el modelo inmutable de dominio."""

    return Report(
        id=_uuid(row["id"]),
        user_id=_uuid(row["user_id"]),
        telegram_chat_id=int(row["telegram_chat_id"]),
        report_kind=ReportKind(row["report_kind"]),
        event_type_id=(
            int(row["event_type_id"])
            if row["event_type_id"] is not None
            else None
        ),
        status=ReportStatus(row["status"]),
        workflow_step=WorkflowStep(row["workflow_step"]),
        latitude=float(row["latitude"]) if row["latitude"] is not None else None,
        longitude=(
            float(row["longitude"]) if row["longitude"] is not None else None
        ),
        location_accuracy=(
            float(row["location_accuracy"])
            if row["location_accuracy"] is not None
            else None
        ),
        description=row["description"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        submitted_at=row["submitted_at"],
    )


def _bigint(value: object, field_name: str) -> int:
    """Valida un entero con el rango de ``BIGINT`` firmado."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} debe ser un número entero")
    if not -(2**63) <= value <= 2**63 - 1:
        raise ValueError(f"{field_name} excede la capacidad de BIGINT")
    return value


def _finite_float(value: object, field_name: str) -> float:
    """Convierte un número y rechaza NaN e infinitos antes de consultar SQL."""

    if isinstance(value, bool):
        raise ValueError(f"{field_name} debe ser un número")
    try:
        normalized = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} debe ser un número") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} debe ser un número finito")
    return normalized


def normalize_description(description: object) -> str:
    """Quita espacios exteriores y exige al menos diez caracteres."""

    if not isinstance(description, str):
        raise ReportValidationError(["La descripción debe ser texto."])
    normalized = description.strip()
    if "\x00" in normalized:
        raise ReportValidationError(
            ["La descripción contiene un carácter no permitido."]
        )
    if len(normalized) < 10:
        raise ReportValidationError(
            ["La descripción debe tener al menos 10 caracteres."]
        )
    return normalized


def report_short_code(report_id: UUID, length: int = 8) -> str:
    """Genera el código breve mostrado al usuario a partir del UUID."""

    if length <= 0 or length > 32:
        raise ValueError("length debe estar entre 1 y 32")
    return report_id.hex[:length].upper()


async def create_draft(
    database: Database,
    user_id: UUID,
    chat_id: int,
    report_kind: ReportKind | str,
    workflow_step: WorkflowStep | str | None = None,
) -> UUID:
    """Cancela el borrador previo y crea uno nuevo de forma atómica.

    El usuario se bloquea durante la transacción. Así, incluso con más de un
    proceso del bot, dos inicios simultáneos no pueden saltarse la regla de un
    único ``DRAFT`` por usuario.
    """

    kind = ReportKind(report_kind)
    expected_step = (
        WorkflowStep.CHOOSE_EVENT_TYPE
        if kind is ReportKind.EVENT
        else WorkflowStep.WAITING_MEDIA
    )
    step = expected_step if workflow_step is None else WorkflowStep(workflow_step)
    if step is not expected_step:
        raise ValueError(
            f"El paso inicial de {kind.value} debe ser {expected_step.value}"
        )

    normalized_chat_id = _bigint(chat_id, "chat_id")
    report_id = uuid4()

    async with transaction(database) as connection:
        # La FK comprobaría también la existencia, pero el bloqueo serializa
        # todos los intentos de iniciar un reporte para este usuario.
        locked_user_id = await connection.fetchval(
            "SELECT id FROM telegram_users WHERE id = $1 FOR UPDATE",
            user_id,
        )
        if locked_user_id is None:
            raise ValueError("El usuario de Telegram no existe en la base de datos")

        await connection.execute(
            """
            UPDATE reports
            SET
                status = 'CANCELLED',
                workflow_step = 'CANCELLED',
                updated_at = NOW()
            WHERE user_id = $1
              AND status = 'DRAFT'
            """,
            user_id,
        )

        inserted_id = await connection.fetchval(
            """
            INSERT INTO reports (
                id,
                user_id,
                telegram_chat_id,
                report_kind,
                status,
                workflow_step
            )
            VALUES ($1, $2, $3, $4, 'DRAFT', $5)
            RETURNING id
            """,
            report_id,
            user_id,
            normalized_chat_id,
            kind.value,
            step.value,
        )

    if inserted_id is None:
        raise RuntimeError("PostgreSQL no devolvió el UUID del reporte")
    return _uuid(inserted_id)


async def cancel_active_draft(database: Database, user_id: UUID) -> bool:
    """Cancela lógicamente el borrador activo, sin borrar sus evidencias."""

    async with transaction(database) as connection:
        cancelled_id = await connection.fetchval(
            """
            UPDATE reports
            SET
                status = 'CANCELLED',
                workflow_step = 'CANCELLED',
                updated_at = NOW()
            WHERE user_id = $1
              AND status = 'DRAFT'
            RETURNING id
            """,
            user_id,
        )
    return cancelled_id is not None


async def get_report(database: Database, report_id: UUID) -> Report | None:
    """Busca un reporte por UUID."""

    async with acquire_connection(database) as connection:
        row = await connection.fetchrow(
            "SELECT * FROM reports WHERE id = $1",
            report_id,
        )
    return _report_from_record(row) if row is not None else None


async def get_active_draft(database: Database, user_id: UUID) -> Report | None:
    """Obtiene el único borrador activo del usuario, si existe."""

    async with acquire_connection(database) as connection:
        row = await connection.fetchrow(
            """
            SELECT *
            FROM reports
            WHERE user_id = $1
              AND status = 'DRAFT'
            """,
            user_id,
        )
    return _report_from_record(row) if row is not None else None


async def set_event_type(
    database: Database,
    report_id: UUID,
    event_code: EventType | str,
    next_step: WorkflowStep | str = WorkflowStep.WAITING_MEDIA,
) -> bool:
    """Asigna un evento activo y avanza el borrador a evidencias."""

    code = EventType(event_code)
    step = WorkflowStep(next_step)
    if step is not WorkflowStep.WAITING_MEDIA:
        raise ValueError("Al seleccionar el evento se debe avanzar a WAITING_MEDIA")

    async with transaction(database) as connection:
        updated_id = await connection.fetchval(
            """
            UPDATE reports AS report
            SET
                event_type_id = event_type.id,
                workflow_step = $3,
                updated_at = NOW()
            FROM event_types AS event_type
            WHERE report.id = $1
              AND event_type.code = $2
              AND event_type.is_active = TRUE
              AND report.report_kind = 'EVENT'
              AND report.status = 'DRAFT'
              AND report.workflow_step = 'CHOOSE_EVENT_TYPE'
            RETURNING report.id
            """,
            report_id,
            code.value,
            step.value,
        )
    return updated_id is not None


async def update_workflow_step(
    database: Database,
    report_id: UUID,
    workflow_step: WorkflowStep | str,
) -> bool:
    """Realiza una transición activa solo si sus prerrequisitos ya existen.

    Los métodos especializados son preferibles, pero este helper resulta útil
    para recuperar una conversación. No permite marcar un reporte como enviado
    o cancelado; esas operaciones tienen sus propias validaciones.
    """

    target = WorkflowStep(workflow_step)
    active_steps = {
        WorkflowStep.CHOOSE_EVENT_TYPE,
        WorkflowStep.WAITING_MEDIA,
        WorkflowStep.WAITING_LOCATION,
        WorkflowStep.WAITING_DESCRIPTION,
    }
    if target not in active_steps:
        raise ValueError("Use submit_report o cancel_active_draft para cerrar el flujo")

    async with transaction(database) as connection:
        updated_id = await connection.fetchval(
            """
            UPDATE reports AS report
            SET workflow_step = $2, updated_at = NOW()
            WHERE report.id = $1
              AND report.status = 'DRAFT'
              AND (
                    report.workflow_step = $2
                    OR (
                        report.workflow_step = 'CHOOSE_EVENT_TYPE'
                        AND $2 = 'WAITING_MEDIA'
                        AND report.report_kind = 'EVENT'
                        AND report.event_type_id IS NOT NULL
                    )
                    OR (
                        report.workflow_step = 'WAITING_MEDIA'
                        AND $2 = 'WAITING_LOCATION'
                        AND EXISTS (
                            SELECT 1
                            FROM report_media AS media
                            WHERE media.report_id = report.id
                        )
                    )
                    OR (
                        report.workflow_step = 'WAITING_LOCATION'
                        AND $2 = 'WAITING_DESCRIPTION'
                        AND report.latitude IS NOT NULL
                        AND report.longitude IS NOT NULL
                    )
              )
            RETURNING report.id
            """,
            report_id,
            target.value,
        )
    return updated_id is not None


async def set_location(
    database: Database,
    report_id: UUID,
    latitude: float,
    longitude: float,
    accuracy: float | None,
    next_step: WorkflowStep | str = WorkflowStep.WAITING_DESCRIPTION,
) -> bool:
    """Valida y guarda una ubicación; luego solicita la descripción."""

    normalized_next_step = WorkflowStep(next_step)
    if normalized_next_step is not WorkflowStep.WAITING_DESCRIPTION:
        raise ValueError(
            "Después de guardar la ubicación se debe avanzar a "
            "WAITING_DESCRIPTION"
        )

    normalized_latitude = _finite_float(latitude, "latitude")
    normalized_longitude = _finite_float(longitude, "longitude")
    if not -90.0 <= normalized_latitude <= 90.0:
        raise ValueError("latitude debe estar entre -90 y 90")
    if not -180.0 <= normalized_longitude <= 180.0:
        raise ValueError("longitude debe estar entre -180 y 180")

    normalized_accuracy: float | None = None
    if accuracy is not None:
        normalized_accuracy = _finite_float(accuracy, "accuracy")
        if normalized_accuracy < 0:
            raise ValueError("accuracy no puede ser negativa")

    async with transaction(database) as connection:
        updated_id = await connection.fetchval(
            """
            UPDATE reports
            SET
                latitude = $2,
                longitude = $3,
                location_accuracy = $4,
                workflow_step = $5,
                updated_at = NOW()
            WHERE id = $1
              AND status = 'DRAFT'
              AND workflow_step = 'WAITING_LOCATION'
            RETURNING id
            """,
            report_id,
            normalized_latitude,
            normalized_longitude,
            normalized_accuracy,
            normalized_next_step.value,
        )
    return updated_id is not None


async def submit_report(
    database: Database,
    report_id: UUID,
    description: str,
) -> Report:
    """Valida todos los requisitos y envía el reporte atómicamente.

    La fila se bloquea mientras se comprueban usuario, tipo, evento, evidencias
    y ubicación. Si algo falta, la transacción no modifica el borrador y la
    excepción enumera los problemas encontrados.
    """

    normalized_description = normalize_description(description)

    async with transaction(database) as connection:
        row = await connection.fetchrow(
            "SELECT * FROM reports WHERE id = $1 FOR UPDATE",
            report_id,
        )
        if row is None:
            raise ReportNotFoundError("No existe el reporte solicitado")
        if row["status"] != ReportStatus.DRAFT.value:
            raise InvalidReportStateError("El reporte ya no es un borrador activo")
        if row["workflow_step"] != WorkflowStep.WAITING_DESCRIPTION.value:
            raise InvalidReportStateError(
                "El reporte todavía no está esperando una descripción"
            )

        problems: list[str] = []
        user_exists = await connection.fetchval(
            "SELECT EXISTS(SELECT 1 FROM telegram_users WHERE id = $1)",
            row["user_id"],
        )
        if not user_exists:
            problems.append("El usuario asociado no existe.")

        try:
            kind = ReportKind(row["report_kind"])
        except ValueError:
            kind = None
            problems.append("El tipo de reporte no es válido.")

        if kind is ReportKind.EVENT:
            if row["event_type_id"] is None:
                problems.append("El evento no tiene un tipo seleccionado.")
            else:
                event_exists = await connection.fetchval(
                    """
                    SELECT EXISTS(
                        SELECT 1
                        FROM event_types
                        WHERE id = $1 AND is_active = TRUE
                    )
                    """,
                    row["event_type_id"],
                )
                if not event_exists:
                    problems.append("El tipo de evento no existe o está inactivo.")
        elif kind is ReportKind.INCIDENT and row["event_type_id"] is not None:
            problems.append("Un incidente no puede tener un tipo de evento.")

        media_count = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM report_media WHERE report_id = $1",
                report_id,
            )
            or 0
        )
        if media_count < 1:
            problems.append("Debe registrar al menos una foto o un video.")

        if row["latitude"] is None:
            problems.append("Falta la latitud.")
        elif not -90.0 <= float(row["latitude"]) <= 90.0:
            problems.append("La latitud guardada no es válida.")
        if row["longitude"] is None:
            problems.append("Falta la longitud.")
        elif not -180.0 <= float(row["longitude"]) <= 180.0:
            problems.append("La longitud guardada no es válida.")

        if problems:
            raise ReportValidationError(problems)

        submitted_row = await connection.fetchrow(
            """
            UPDATE reports
            SET
                description = $2,
                status = 'SUBMITTED',
                workflow_step = 'COMPLETED',
                submitted_at = NOW(),
                updated_at = NOW()
            WHERE id = $1
              AND status = 'DRAFT'
              AND workflow_step = 'WAITING_DESCRIPTION'
            RETURNING *
            """,
            report_id,
            normalized_description,
        )
        if submitted_row is None:
            raise InvalidReportStateError(
                "El reporte cambió de estado antes de poder enviarse"
            )

    return _report_from_record(submitted_row)


__all__ = [
    "InvalidReportStateError",
    "ReportNotFoundError",
    "ReportRepositoryError",
    "ReportValidationError",
    "cancel_active_draft",
    "create_draft",
    "get_active_draft",
    "get_report",
    "normalize_description",
    "report_short_code",
    "set_event_type",
    "set_location",
    "submit_report",
    "update_workflow_step",
]
