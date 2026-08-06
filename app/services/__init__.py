"""Servicios que integran el dominio con APIs externas."""

from app.models import TelegramMediaData
from app.services.telegram_media import (
    extract_media_data,
    get_temporary_telegram_file_url,
    send_report_media,
)

__all__ = [
    "extract_media_data",
    "get_temporary_telegram_file_url",
    "send_report_media",
    "TelegramMediaData",
]
