"""Extracción y reenvío de archivos alojados por Telegram.

Este módulo nunca descarga evidencias. Solo persiste y reutiliza ``file_id``.
Eso mantiene al servidor sin copias locales y evita guardar las URL temporales
que Telegram genera mediante ``get_file``.
"""

from collections.abc import Mapping
from datetime import timedelta
from typing import Any
from uuid import UUID

from telegram import Message
from telegram.ext import ContextTypes

from app.models import MediaType, TelegramMediaData, TelegramMessageType
from app.repositories.media import list_report_media


def _duration_in_seconds(value: int | timedelta) -> int:
    """Normaliza la transición de PTB 22 desde enteros hacia ``timedelta``."""

    if isinstance(value, timedelta):
        return int(value.total_seconds())
    return value


def extract_media_data(message: Message) -> TelegramMediaData | None:
    """Extrae metadatos de una foto, vídeo o documento compatible.

    Telegram ofrece varias resoluciones en ``message.photo``; la última es la
    de mayor tamaño. Para documentos se exige un MIME ``image/*`` o ``video/*``.
    El archivo no se obtiene con ``get_file`` y tampoco se descarga.
    """

    if message.photo:
        photo = message.photo[-1]
        return TelegramMediaData(
            media_type=MediaType.PHOTO,
            telegram_message_type=TelegramMessageType.PHOTO,
            file_id=photo.file_id,
            file_unique_id=photo.file_unique_id,
            file_size=photo.file_size,
            mime_type="image/jpeg",
            original_file_name=None,
            width=photo.width,
            height=photo.height,
            duration_seconds=None,
        )

    if message.video is not None:
        video = message.video
        return TelegramMediaData(
            media_type=MediaType.VIDEO,
            telegram_message_type=TelegramMessageType.VIDEO,
            file_id=video.file_id,
            file_unique_id=video.file_unique_id,
            file_size=video.file_size,
            mime_type=video.mime_type,
            original_file_name=video.file_name,
            width=video.width,
            height=video.height,
            duration_seconds=_duration_in_seconds(video.duration),
        )

    if message.document is None:
        return None

    document = message.document
    mime_type = (document.mime_type or "").lower()
    if mime_type.startswith("image/"):
        media_type = MediaType.PHOTO
    elif mime_type.startswith("video/"):
        media_type = MediaType.VIDEO
    else:
        # El nombre del archivo es dato no confiable: no se usa para saltarse
        # la validación MIME ni para ejecutar acciones en el servidor.
        return None

    return TelegramMediaData(
        media_type=media_type,
        telegram_message_type=TelegramMessageType.DOCUMENT,
        file_id=document.file_id,
        file_unique_id=document.file_unique_id,
        file_size=document.file_size,
        mime_type=document.mime_type,
        original_file_name=document.file_name,
        width=None,
        height=None,
        duration_seconds=None,
    )


def _field(record: object, name: str) -> Any:
    """Lee tanto dataclasses como ``asyncpg.Record`` sin acoplar el servicio."""

    if isinstance(record, Mapping):
        return record[name]
    return getattr(record, name)


async def send_report_media(
    context: ContextTypes.DEFAULT_TYPE,
    destination_chat_id: int,
    report_id: UUID,
) -> int:
    """Reenvía todas las evidencias de un reporte usando sus ``file_id``.

    Returns:
        Cantidad de archivos enviados correctamente.
    """

    pool = context.application.bot_data["db_pool"]
    records = await list_report_media(pool, report_id)

    sent_count = 0
    for record in records:
        message_type = TelegramMessageType(_field(record, "telegram_message_type"))
        file_id = str(_field(record, "telegram_file_id"))
        caption = _field(record, "caption")

        if message_type is TelegramMessageType.PHOTO:
            await context.bot.send_photo(
                chat_id=destination_chat_id,
                photo=file_id,
                caption=caption,
            )
        elif message_type is TelegramMessageType.VIDEO:
            await context.bot.send_video(
                chat_id=destination_chat_id,
                video=file_id,
                caption=caption,
            )
        else:
            await context.bot.send_document(
                chat_id=destination_chat_id,
                document=file_id,
                caption=caption,
            )
        sent_count += 1

    return sent_count


async def get_temporary_telegram_file_url(
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
) -> str:
    """Solicita bajo demanda la URL temporal de un archivo de Telegram.

    Esta URL puede contener información vinculada al token del bot: no debe
    publicarse ni persistirse. Cuando expire hay que solicitarla nuevamente.
    El valor permanente en PostgreSQL debe seguir siendo ``file_id``.
    """

    telegram_file = await context.bot.get_file(file_id)
    if not telegram_file.file_path:
        raise RuntimeError("Telegram no devolvió una ruta temporal para el archivo")
    return str(telegram_file.file_path)


__all__ = [
    "TelegramMediaData",
    "extract_media_data",
    "get_temporary_telegram_file_url",
    "send_report_media",
]
