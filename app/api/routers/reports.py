"""Endpoints de consulta de reportes enviados."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import PoolDep
from app.api.schemas import (
    EventTypeOut,
    PageCursor,
    ReportOut,
    ReportPageOut,
)
from app.repositories.exports import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    get_submitted_report,
    list_event_types,
    list_submitted_reports,
)


router = APIRouter(prefix="/v1", tags=["reportes"])


@router.get(
    "/reports",
    response_model=ReportPageOut,
    summary="Lista incremental de reportes enviados",
)
async def read_reports(
    pool: PoolDep,
    since: Annotated[
        datetime | None,
        Query(
            description=(
                "Instante ISO-8601 con zona horaria. Devuelve lo modificado "
                "después de este valor. Usa el `next.since` de la página previa."
            )
        ),
    ] = None,
    cursor_id: Annotated[
        UUID | None,
        Query(description="`next.cursor_id` de la página previa. Requiere `since`."),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_PAGE_SIZE, description="Reportes por página"),
    ] = DEFAULT_PAGE_SIZE,
) -> ReportPageOut:
    """Recorre los reportes enviados ordenados por última modificación.

    Está pensado para sincronización continua: se guarda el cursor devuelto y
    se vuelve a llamar con él. Un reporte modificado después de haberse leído
    reaparece en una página posterior, así que el consumidor debe tratar la
    ingesta como un *upsert* por ``id`` y no como un simple *insert*.
    """

    try:
        page = await list_submitted_reports(
            pool,
            since=since,
            cursor_id=cursor_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    next_cursor = None
    if page.next_id is not None and page.next_updated_at is not None:
        next_cursor = PageCursor(since=page.next_updated_at, cursor_id=page.next_id)

    return ReportPageOut(
        items=[ReportOut.from_domain(item) for item in page.items],
        next=next_cursor,
    )


@router.get(
    "/reports/{report_id}",
    response_model=ReportOut,
    summary="Detalle de un reporte enviado",
    responses={404: {"description": "No existe o todavía no fue enviado"}},
)
async def read_report(report_id: UUID, pool: PoolDep) -> ReportOut:
    """Devuelve un único reporte con sus evidencias."""

    exported = await get_submitted_report(pool, report_id)
    if exported is None:
        # Se responde igual para un UUID inexistente y para un borrador: la
        # diferencia revelaría la existencia de reportes aún no enviados.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe un reporte enviado con ese identificador",
        )
    return ReportOut.from_domain(exported)


@router.get(
    "/event-types",
    response_model=list[EventTypeOut],
    summary="Catálogo de tipos de evento",
)
async def read_event_types(pool: PoolDep) -> list[EventTypeOut]:
    """Permite traducir `event_type_code` sin replicar la tabla."""

    rows = await list_event_types(pool)
    return [
        EventTypeOut(
            code=row["code"],
            name=row["name"],
            is_active=row["is_active"],
        )
        for row in rows
    ]
