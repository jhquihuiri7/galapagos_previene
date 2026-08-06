"""Persistencia de metadatos de fotos y videos alojados por Telegram.

Solo se guarda ``telegram_file_id`` y la información necesaria para reenviar el
archivo. Este repositorio no solicita URLs, no descarga datos y no confía en el
nombre original para tomar decisiones sobre el tipo de contenido.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final
from uuid import UUID, uuid4

from app.models import (
    MediaType,
    ReportMedia,
    ReportMediaCreate,
    ReportStatus,
    TelegramMessageType,
    WorkflowStep,
)
from app.repositories import Database, acquire_connection, transaction
from app.repositories.reports import (
    InvalidReportStateError,
    ReportNotFoundError,
)


DEFAULT_MAX_MEDIA_FILES: Final[int] = 10


class InvalidMediaError(ValueError):
    """Los metadatos del archivo no cumplen las reglas del dominio."""


class MediaLimitReachedError(RuntimeError):
    """El reporte ya alcanzó el máximo configurado de evidencias."""

    def __init__(self, max_files: int) -> None:
        self.max_files = max_files
        super().__init__(
            f"El reporte ya alcanzó el límite de {max_files} archivos."
        )


class NoMediaFilesError(RuntimeError):
    """No se puede finalizar la etapa sin una foto o un video."""


def _uuid(value: object) -> UUID:
    """Normaliza UUID devueltos por asyncpg o dobles de prueba."""

    return value if isinstance(value, UUID) else UUID(str(value))


def _media_from_record(row: Mapping[str, Any]) -> ReportMedia:
    """Convierte una fila en el modelo inmutable usado por los servicios."""

    return ReportMedia(
        id=_uuid(row["id"]),
        report_id=_uuid(row["report_id"]),
        media_type=MediaType(row["media_type"]),
        telegram_message_type=TelegramMessageType(row["telegram_message_type"]),
        telegram_file_id=str(row["telegram_file_id"]),
        telegram_file_unique_id=str(row["telegram_file_unique_id"]),
        telegram_message_id=int(row["telegram_message_id"]),
        telegram_media_group_id=row["telegram_media_group_id"],
        mime_type=row["mime_type"],
        original_file_name=row["original_file_name"],
        file_size=int(row["file_size"]) if row["file_size"] is not None else None,
        width=int(row["width"]) if row["width"] is not None else None,
        height=int(row["height"]) if row["height"] is not None else None,
        duration_seconds=(
            int(row["duration_seconds"])
            if row["duration_seconds"] is not None
            else None
        ),
        caption=row["caption"],
        created_at=row["created_at"],
    )


def _integer(
    value: object,
    field_name: str,
    *,
    minimum: int,
    maximum: int,
    optional: bool = True,
) -> int | None:
    """Valida enteros de Telegram antes de entregarlos a asyncpg."""

    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidMediaError(f"{field_name} debe ser un número entero")
    if not minimum <= value <= maximum:
        raise InvalidMediaError(
            f"{field_name} debe estar entre {minimum} y {maximum}"
        )
    return value


def _optional_text(
    value: object,
    field_name: str,
    *,
    max_length: int | None = None,
) -> str | None:
    """Valida texto no ejecutable recibido desde Telegram."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidMediaError(f"{field_name} debe ser texto o None")
    if "\x00" in value:
        raise InvalidMediaError(f"{field_name} contiene un carácter no permitido")
    normalized = value.strip()
    if not normalized:
        return None
    if max_length is not None and len(normalized) > max_length:
        raise InvalidMediaError(
            f"{field_name} supera el máximo de {max_length} caracteres"
        )
    return normalized


def _required_text(value: object, field_name: str, max_length: int | None) -> str:
    """Normaliza un identificador obligatorio de Telegram."""

    normalized = _optional_text(
        value,
        field_name,
        max_length=max_length,
    )
    if normalized is None:
        raise InvalidMediaError(f"{field_name} no puede estar vacío")
    return normalized


def _validated_media_values(media: ReportMediaCreate) -> tuple[object, ...]:
    """Valida consistencia, MIME y rangos; devuelve valores listos para SQL."""

    try:
        media_type = MediaType(media.media_type)
        message_type = TelegramMessageType(media.telegram_message_type)
    except ValueError as exc:
        raise InvalidMediaError("El tipo de archivo no es válido") from exc

    if message_type is TelegramMessageType.PHOTO and media_type is not MediaType.PHOTO:
        raise InvalidMediaError("Un mensaje PHOTO debe contener media_type PHOTO")
    if message_type is TelegramMessageType.VIDEO and media_type is not MediaType.VIDEO:
        raise InvalidMediaError("Un mensaje VIDEO debe contener media_type VIDEO")

    file_id = _required_text(media.telegram_file_id, "telegram_file_id", None)
    unique_id = _required_text(
        media.telegram_file_unique_id,
        "telegram_file_unique_id",
        255,
    )
    message_id = _integer(
        media.telegram_message_id,
        "telegram_message_id",
        minimum=1,
        maximum=2**63 - 1,
        optional=False,
    )
    media_group_id = _optional_text(
        media.telegram_media_group_id,
        "telegram_media_group_id",
        max_length=255,
    )
    mime_type = _optional_text(media.mime_type, "mime_type", max_length=128)
    if mime_type is not None:
        mime_type = mime_type.lower()
        major, separator, minor = mime_type.partition("/")
        if not separator or not major or not minor or any(char.isspace() for char in mime_type):
            raise InvalidMediaError("mime_type no tiene un formato MIME válido")
        expected_major = "image" if media_type is MediaType.PHOTO else "video"
        if major != expected_major:
            raise InvalidMediaError(
                f"mime_type debe comenzar con {expected_major}/ para este archivo"
            )
    elif message_type is TelegramMessageType.DOCUMENT:
        # Para documentos no se puede inferir de forma segura el contenido por
        # la extensión ni por el nombre proporcionado por el usuario.
        raise InvalidMediaError("Un documento debe incluir un mime_type válido")

    original_file_name = _optional_text(
        media.original_file_name,
        "original_file_name",
    )
    file_size = _integer(
        media.file_size,
        "file_size",
        minimum=0,
        maximum=2**63 - 1,
    )
    width = _integer(
        media.width,
        "width",
        minimum=1,
        maximum=2**31 - 1,
    )
    height = _integer(
        media.height,
        "height",
        minimum=1,
        maximum=2**31 - 1,
    )
    duration = _integer(
        media.duration_seconds,
        "duration_seconds",
        minimum=0,
        maximum=2**31 - 1,
    )
    caption = _optional_text(media.caption, "caption")

    return (
        media_type.value,
        message_type.value,
        file_id,
        unique_id,
        message_id,
        media_group_id,
        mime_type,
        original_file_name,
        file_size,
        width,
        height,
        duration,
        caption,
    )


async def create_report_media(
    database: Database,
    report_id: UUID,
    media: ReportMediaCreate,
    max_files: int = DEFAULT_MAX_MEDIA_FILES,
) -> bool:
    """Guarda una evidencia de forma atómica.

    Returns:
        ``True`` si se insertó; ``False`` si el mismo ``message_id`` ya estaba
        registrado para el reporte (por ejemplo, por reenvío de un update).

    Raises:
        MediaLimitReachedError: Si ya se alcanzó ``max_files``.
        InvalidReportStateError: Si el reporte no espera evidencias.
    """

    if isinstance(max_files, bool) or not isinstance(max_files, int) or max_files <= 0:
        raise ValueError("max_files debe ser un entero mayor que cero")
    values = _validated_media_values(media)

    async with transaction(database) as connection:
        report = await connection.fetchrow(
            """
            SELECT status, workflow_step
            FROM reports
            WHERE id = $1
            FOR UPDATE
            """,
            report_id,
        )
        if report is None:
            raise ReportNotFoundError("No existe el reporte solicitado")

        # Se comprueba el duplicado antes del estado y del límite. Así una
        # actualización repetida sigue siendo idempotente incluso si el usuario
        # ya pulsó "Finalizar fotos y videos".
        duplicate = await connection.fetchval(
            """
            SELECT EXISTS(
                SELECT 1
                FROM report_media
                WHERE report_id = $1
                  AND telegram_message_id = $2
            )
            """,
            report_id,
            values[4],
        )
        if duplicate:
            return False

        if (
            report["status"] != ReportStatus.DRAFT.value
            or report["workflow_step"] != WorkflowStep.WAITING_MEDIA.value
        ):
            raise InvalidReportStateError(
                "El reporte no está esperando fotos o videos"
            )

        current_count = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM report_media WHERE report_id = $1",
                report_id,
            )
            or 0
        )
        if current_count >= max_files:
            raise MediaLimitReachedError(max_files)

        inserted_id = await connection.fetchval(
            """
            INSERT INTO report_media (
                id,
                report_id,
                media_type,
                telegram_message_type,
                telegram_file_id,
                telegram_file_unique_id,
                telegram_message_id,
                telegram_media_group_id,
                mime_type,
                original_file_name,
                file_size,
                width,
                height,
                duration_seconds,
                caption
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8,
                $9, $10, $11, $12, $13, $14, $15
            )
            ON CONFLICT (report_id, telegram_message_id) DO NOTHING
            RETURNING id
            """,
            uuid4(),
            report_id,
            *values,
        )

    return inserted_id is not None


async def count_report_media(database: Database, report_id: UUID) -> int:
    """Cuenta las filas de evidencia asociadas al reporte."""

    async with acquire_connection(database) as connection:
        count = await connection.fetchval(
            "SELECT COUNT(*) FROM report_media WHERE report_id = $1",
            report_id,
        )
    return int(count or 0)


async def list_report_media(
    database: Database,
    report_id: UUID,
) -> Sequence[ReportMedia]:
    """Lista evidencias en el mismo orden en que fueron registradas."""

    async with acquire_connection(database) as connection:
        rows = await connection.fetch(
            """
            SELECT *
            FROM report_media
            WHERE report_id = $1
            ORDER BY created_at ASC, id ASC
            """,
            report_id,
        )
    return [_media_from_record(row) for row in rows]


async def finalize_media_step(database: Database, report_id: UUID) -> int:
    """Comprueba que haya evidencias y avanza a ``WAITING_LOCATION``.

    El bloqueo de la fila es el mismo que usa :func:`create_report_media`, por
    lo que agregar un archivo y finalizar no pueden intercalarse de manera que
    el contador mostrado no corresponda con el estado persistido.

    Returns:
        Cantidad definitiva de archivos registrados.
    """

    async with transaction(database) as connection:
        report = await connection.fetchrow(
            """
            SELECT status, workflow_step
            FROM reports
            WHERE id = $1
            FOR UPDATE
            """,
            report_id,
        )
        if report is None:
            raise ReportNotFoundError("No existe el reporte solicitado")
        if (
            report["status"] != ReportStatus.DRAFT.value
            or report["workflow_step"] != WorkflowStep.WAITING_MEDIA.value
        ):
            raise InvalidReportStateError(
                "El reporte no está esperando fotos o videos"
            )

        media_count = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM report_media WHERE report_id = $1",
                report_id,
            )
            or 0
        )
        if media_count < 1:
            raise NoMediaFilesError(
                "Debes registrar al menos una foto o un video antes de continuar."
            )

        updated_id = await connection.fetchval(
            """
            UPDATE reports
            SET workflow_step = 'WAITING_LOCATION', updated_at = NOW()
            WHERE id = $1
              AND status = 'DRAFT'
              AND workflow_step = 'WAITING_MEDIA'
            RETURNING id
            """,
            report_id,
        )
        if updated_id is None:
            raise InvalidReportStateError(
                "El reporte cambió de estado antes de finalizar los archivos"
            )

    return media_count


__all__ = [
    "DEFAULT_MAX_MEDIA_FILES",
    "InvalidMediaError",
    "MediaLimitReachedError",
    "NoMediaFilesError",
    "count_report_media",
    "create_report_media",
    "finalize_media_step",
    "list_report_media",
]
