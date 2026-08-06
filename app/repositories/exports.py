"""Consultas de solo lectura que alimentan la API pública.

Se mantienen separadas de :mod:`app.repositories.reports` porque responden a
necesidades distintas: aquí no se valida ni se muta nada, y las consultas están
pensadas para recorrer la tabla de forma incremental desde un servicio externo.
El rol de PostgreSQL que usa la API solo tiene ``SELECT`` (ver
``sql/api_readonly.sql``), así que este módulo es el límite real de lo que
puede salir del sistema.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from app.models import Report, ReportMedia, ReportStatus
from app.repositories import Database, acquire_connection

# Los conversores de fila son privados del paquete, no del módulo: reutilizarlos
# garantiza que la API interprete los tipos exactamente igual que el bot.
from app.repositories.media import _media_from_record
from app.repositories.reports import _report_from_record


# Cota superior de filas por página. Protege a PostgreSQL de una petición que
# pida un límite arbitrariamente grande.
MAX_PAGE_SIZE: Final[int] = 200
DEFAULT_PAGE_SIZE: Final[int] = 50


@dataclass(frozen=True, slots=True)
class ExportedReport:
    """Reporte enviado junto con el contexto que necesita un consumidor.

    ``event_type_code`` evita que el otro servicio tenga que replicar la tabla
    ``event_types`` para traducir un identificador numérico.
    """

    report: Report
    event_type_code: str | None
    event_type_name: str | None
    media: Sequence[ReportMedia]


@dataclass(frozen=True, slots=True)
class ReportPage:
    """Página de resultados y el cursor para pedir la siguiente."""

    items: Sequence[ExportedReport]
    next_updated_at: datetime | None
    next_id: UUID | None

    @property
    def has_more(self) -> bool:
        """Indica si quedó al menos un elemento fuera de esta página."""

        return self.next_id is not None


def _clamp_limit(limit: int) -> int:
    """Normaliza el tamaño de página solicitado por el cliente."""

    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("limit debe ser un número entero")
    if limit < 1:
        raise ValueError("limit debe ser mayor que cero")
    return min(limit, MAX_PAGE_SIZE)


def _media_by_report(
    rows: Sequence[Mapping[str, Any]],
) -> dict[UUID, list[ReportMedia]]:
    """Agrupa las evidencias por reporte en una sola pasada."""

    grouped: dict[UUID, list[ReportMedia]] = {}
    for row in rows:
        media = _media_from_record(row)
        grouped.setdefault(media.report_id, []).append(media)
    return grouped


async def _fetch_media_for(
    connection: Any,
    report_ids: Sequence[UUID],
) -> dict[UUID, list[ReportMedia]]:
    """Trae las evidencias de varios reportes con una única consulta.

    Recorrer los reportes llamando a ``list_report_media`` funcionaría, pero
    generaría una consulta por fila (N+1). Con ``= ANY($1)`` el coste no crece
    con el tamaño de la página.
    """

    if not report_ids:
        return {}

    rows = await connection.fetch(
        """
        SELECT *
        FROM report_media
        WHERE report_id = ANY($1::uuid[])
        ORDER BY report_id, created_at ASC, id ASC
        """,
        list(report_ids),
    )
    return _media_by_report(rows)


async def list_submitted_reports(
    database: Database,
    *,
    since: datetime | None = None,
    cursor_id: UUID | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> ReportPage:
    """Devuelve reportes enviados ordenados por ``(updated_at, id)``.

    El cursor es compuesto a propósito. Ordenar solo por ``updated_at`` no
    basta: si dos reportes comparten el instante exacto, una paginación por
    marca de tiempo puede saltarse uno o repetirlo. El ``id`` desempata y hace
    que el recorrido sea estable aunque lleguen reportes nuevos entre páginas.

    Args:
        since: Devuelve lo modificado a partir de este instante (inclusive si
            no se acompaña de ``cursor_id``). ``None`` recorre desde el inicio.
        cursor_id: ``next_id`` de la página anterior. Requiere ``since``.
        limit: Máximo de reportes; se recorta a :data:`MAX_PAGE_SIZE`.

    Raises:
        ValueError: Si ``cursor_id`` llega sin ``since`` o ``limit`` no es
            válido.
    """

    page_size = _clamp_limit(limit)
    if cursor_id is not None and since is None:
        raise ValueError("cursor_id requiere el valor since de la misma página")

    # Se pide una fila extra para saber si hay siguiente página sin ejecutar
    # un COUNT(*) adicional sobre toda la tabla.
    async with acquire_connection(database) as connection:
        rows = await connection.fetch(
            """
            SELECT
                r.*,
                e.code AS event_type_code,
                e.name AS event_type_name
            FROM reports AS r
            LEFT JOIN event_types AS e ON e.id = r.event_type_id
            WHERE r.status = $1
              AND (
                    $2::timestamptz IS NULL
                    OR r.updated_at > $2::timestamptz
                    OR (
                        $3::uuid IS NOT NULL
                        AND r.updated_at = $2::timestamptz
                        AND r.id > $3::uuid
                    )
              )
            ORDER BY r.updated_at ASC, r.id ASC
            LIMIT $4
            """,
            ReportStatus.SUBMITTED.value,
            since,
            cursor_id,
            page_size + 1,
        )

        has_more = len(rows) > page_size
        rows = rows[:page_size]

        media = await _fetch_media_for(connection, [_row_id(row) for row in rows])

    items = [
        ExportedReport(
            report=_report_from_record(row),
            event_type_code=row["event_type_code"],
            event_type_name=row["event_type_name"],
            media=tuple(media.get(_row_id(row), ())),
        )
        for row in rows
    ]

    last = items[-1] if items and has_more else None
    return ReportPage(
        items=tuple(items),
        next_updated_at=last.report.updated_at if last is not None else None,
        next_id=last.report.id if last is not None else None,
    )


def _row_id(row: Mapping[str, Any]) -> UUID:
    """Extrae el UUID de la fila sin construir el modelo completo."""

    value = row["id"]
    return value if isinstance(value, UUID) else UUID(str(value))


async def get_submitted_report(
    database: Database,
    report_id: UUID,
) -> ExportedReport | None:
    """Busca un único reporte enviado con sus evidencias.

    Los borradores y los reportes cancelados devuelven ``None``: son estado
    interno del flujo del bot y no forman parte del contrato público.
    """

    async with acquire_connection(database) as connection:
        row = await connection.fetchrow(
            """
            SELECT
                r.*,
                e.code AS event_type_code,
                e.name AS event_type_name
            FROM reports AS r
            LEFT JOIN event_types AS e ON e.id = r.event_type_id
            WHERE r.id = $1
              AND r.status = $2
            """,
            report_id,
            ReportStatus.SUBMITTED.value,
        )
        if row is None:
            return None

        media = await _fetch_media_for(connection, [report_id])

    return ExportedReport(
        report=_report_from_record(row),
        event_type_code=row["event_type_code"],
        event_type_name=row["event_type_name"],
        media=tuple(media.get(report_id, ())),
    )


async def get_submitted_media(
    database: Database,
    media_id: UUID,
) -> ReportMedia | None:
    """Obtiene una evidencia solo si su reporte ya fue enviado.

    La comprobación del estado del reporte se hace aquí, en la misma consulta,
    para que el endpoint de descarga no pueda servir archivos de un borrador
    por olvidar el filtro.
    """

    async with acquire_connection(database) as connection:
        row = await connection.fetchrow(
            """
            SELECT m.*
            FROM report_media AS m
            JOIN reports AS r ON r.id = m.report_id
            WHERE m.id = $1
              AND r.status = $2
            """,
            media_id,
            ReportStatus.SUBMITTED.value,
        )

    return _media_from_record(row) if row is not None else None


async def list_event_types(database: Database) -> Sequence[Mapping[str, Any]]:
    """Devuelve el catálogo de tipos de evento, activos e inactivos.

    Los inactivos se incluyen porque un reporte histórico puede referirse a uno
    de ellos y el consumidor necesita poder traducir el código igualmente.
    """

    async with acquire_connection(database) as connection:
        rows = await connection.fetch(
            """
            SELECT id, code, name, is_active
            FROM event_types
            ORDER BY id ASC
            """
        )
    return [dict(row) for row in rows]


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "ExportedReport",
    "ReportPage",
    "get_submitted_media",
    "get_submitted_report",
    "list_event_types",
    "list_submitted_reports",
]
