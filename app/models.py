"""Tipos de dominio compartidos por handlers, servicios y repositorios.

Las enumeraciones heredan de ``str`` para que puedan enviarse directamente a
asyncpg y, a la vez, para impedir que el resto de la aplicación use cadenas
escritas de forma inconsistente. Las dataclasses son inmutables porque
representan una instantánea de una fila o de un archivo recibido.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class ReportKind(str, Enum):
    """Clases de reporte aceptadas por el sistema."""

    EVENT = "EVENT"
    INCIDENT = "INCIDENT"


class EventType(str, Enum):
    """Códigos estables de los tipos de evento precargados en PostgreSQL."""

    RAIN = "RAIN"
    TSUNAMI = "TSUNAMI"
    FIRE = "FIRE"


class ReportStatus(str, Enum):
    """Ciclo de vida de un reporte."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    CANCELLED = "CANCELLED"


class WorkflowStep(str, Enum):
    """Paso persistente del flujo en la tabla ``reports``."""

    CHOOSE_EVENT_TYPE = "CHOOSE_EVENT_TYPE"
    WAITING_MEDIA = "WAITING_MEDIA"
    WAITING_LOCATION = "WAITING_LOCATION"
    WAITING_DESCRIPTION = "WAITING_DESCRIPTION"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class MediaType(str, Enum):
    """Naturaleza del contenido, independientemente de cómo llegó a Telegram."""

    PHOTO = "PHOTO"
    VIDEO = "VIDEO"


class TelegramMessageType(str, Enum):
    """Campo de Telegram que contenía el archivo original."""

    PHOTO = "PHOTO"
    VIDEO = "VIDEO"
    DOCUMENT = "DOCUMENT"


@dataclass(frozen=True, slots=True)
class TelegramMediaData:
    """Metadatos extraídos de un mensaje, sin descargar su archivo.

    ``file_id`` sirve para reenviar el contenido con este mismo bot.
    ``file_unique_id`` identifica el archivo, pero Telegram no permite usarlo
    para descargarlo ni reenviarlo.
    """

    media_type: MediaType
    telegram_message_type: TelegramMessageType
    file_id: str
    file_unique_id: str
    file_size: int | None
    mime_type: str | None
    original_file_name: str | None
    width: int | None
    height: int | None
    duration_seconds: int | None


@dataclass(frozen=True, slots=True)
class ReportMediaCreate:
    """Datos necesarios para insertar una evidencia en ``report_media``."""

    media_type: MediaType
    telegram_message_type: TelegramMessageType
    telegram_file_id: str
    telegram_file_unique_id: str
    telegram_message_id: int
    telegram_media_group_id: str | None
    mime_type: str | None
    original_file_name: str | None
    file_size: int | None
    width: int | None
    height: int | None
    duration_seconds: int | None
    caption: str | None


@dataclass(frozen=True, slots=True)
class Report:
    """Instantánea tipada de una fila de ``reports``."""

    id: UUID
    user_id: UUID
    telegram_chat_id: int
    report_kind: ReportKind
    event_type_id: int | None
    status: ReportStatus
    workflow_step: WorkflowStep
    latitude: float | None
    longitude: float | None
    location_accuracy: float | None
    description: str | None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None


@dataclass(frozen=True, slots=True)
class ReportMedia:
    """Instantánea tipada de una fila de ``report_media``."""

    id: UUID
    report_id: UUID
    media_type: MediaType
    telegram_message_type: TelegramMessageType
    telegram_file_id: str
    telegram_file_unique_id: str
    telegram_message_id: int
    telegram_media_group_id: str | None
    mime_type: str | None
    original_file_name: str | None
    file_size: int | None
    width: int | None
    height: int | None
    duration_seconds: int | None
    caption: str | None
    created_at: datetime


__all__ = [
    "EventType",
    "MediaType",
    "Report",
    "ReportKind",
    "ReportMedia",
    "ReportMediaCreate",
    "ReportStatus",
    "TelegramMediaData",
    "TelegramMessageType",
    "WorkflowStep",
]
