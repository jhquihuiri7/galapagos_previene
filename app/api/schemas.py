"""Contrato público de la API. Nada sale del sistema si no está aquí.

Estos modelos son deliberadamente distintos de los de :mod:`app.models`. Las
filas de PostgreSQL contienen datos que no corresponden a un consumidor
externo —identificadores de chat de Telegram, ``file_id`` reutilizables por el
bot, nombres de las personas que reportan— y devolver el modelo de dominio
directamente haría que cualquier columna nueva se publicase sin decidirlo.

Decisión sobre datos personales: se expone el UUID del usuario, que permite
correlacionar varios reportes de la misma persona, pero no su nombre, alias ni
identificador de Telegram. Si SIGTAR llegara a necesitar contactar a quien
reporta, debe añadirse un campo explícito aquí y revisarse con el responsable
de protección de datos.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.repositories.exports import ExportedReport
from app.models import ReportMedia


class MediaOut(BaseModel):
    """Evidencia asociada a un reporte.

    No se publica ``telegram_file_id``: quien lo tuviera necesitaría el token
    del bot para usarlo, y ese token no sale de esta VM. La descarga se hace
    contra ``content_url``, que sirve el propio servicio.
    """

    id: UUID
    media_type: str = Field(description="PHOTO o VIDEO")
    content_url: str = Field(
        description="Ruta para descargar los bytes del archivo desde esta API"
    )
    mime_type: str | None
    original_file_name: str | None
    file_size: int | None
    width: int | None
    height: int | None
    duration_seconds: int | None
    caption: str | None
    created_at: datetime

    @classmethod
    def from_domain(cls, media: ReportMedia) -> "MediaOut":
        """Proyecta la fila de dominio sobre el contrato público."""

        return cls(
            id=media.id,
            media_type=media.media_type.value,
            content_url=f"/v1/media/{media.id}/content",
            mime_type=media.mime_type,
            original_file_name=media.original_file_name,
            file_size=media.file_size,
            width=media.width,
            height=media.height,
            duration_seconds=media.duration_seconds,
            caption=media.caption,
            created_at=media.created_at,
        )


class ReportOut(BaseModel):
    """Reporte enviado, con su ubicación, descripción y evidencias."""

    id: UUID
    reporter_id: UUID = Field(
        description="UUID estable de quien reporta; no identifica a la persona"
    )
    report_kind: str = Field(description="EVENT o INCIDENT")
    event_type_code: str | None = Field(
        default=None, description="RAIN, TSUNAMI o FIRE; nulo en un INCIDENT"
    )
    event_type_name: str | None = None
    latitude: float | None
    longitude: float | None
    location_accuracy: float | None = Field(
        default=None, description="Radio de precisión en metros informado por Telegram"
    )
    description: str | None
    media: list[MediaOut]
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None

    @classmethod
    def from_domain(cls, exported: ExportedReport) -> "ReportOut":
        """Proyecta el resultado del repositorio sobre el contrato público."""

        report = exported.report
        return cls(
            id=report.id,
            reporter_id=report.user_id,
            report_kind=report.report_kind.value,
            event_type_code=exported.event_type_code,
            event_type_name=exported.event_type_name,
            latitude=report.latitude,
            longitude=report.longitude,
            location_accuracy=report.location_accuracy,
            description=report.description,
            media=[MediaOut.from_domain(item) for item in exported.media],
            created_at=report.created_at,
            updated_at=report.updated_at,
            submitted_at=report.submitted_at,
        )


class PageCursor(BaseModel):
    """Posición desde la que continuar el recorrido incremental."""

    since: datetime = Field(description="Valor para el parámetro `since`")
    cursor_id: UUID = Field(description="Valor para el parámetro `cursor_id`")


class ReportPageOut(BaseModel):
    """Página de reportes y las coordenadas de la siguiente.

    Cuando ``next`` es nulo el consumidor está al día: debe guardar el último
    cursor usado y volver a preguntar más tarde con esos mismos valores.
    """

    items: list[ReportOut]
    next: PageCursor | None = None


class EventTypeOut(BaseModel):
    """Entrada del catálogo de tipos de evento."""

    code: str
    name: str
    is_active: bool


class HealthOut(BaseModel):
    """Resultado de la comprobación de salud del servicio."""

    status: str
    database: str


class ErrorOut(BaseModel):
    """Cuerpo uniforme de los errores, para que SIGTAR no parsee prosa."""

    detail: str


__all__ = [
    "ErrorOut",
    "EventTypeOut",
    "HealthOut",
    "MediaOut",
    "PageCursor",
    "ReportOut",
    "ReportPageOut",
]
