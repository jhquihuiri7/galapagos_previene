"""Extracción y reenvío de medios sin descargar archivos de Telegram."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models import MediaType, TelegramMessageType
from app.services import telegram_media


def _message(
    *,
    photo: tuple[SimpleNamespace, ...] = (),
    video: SimpleNamespace | None = None,
    document: SimpleNamespace | None = None,
) -> SimpleNamespace:
    """Crea el mínimo contrato de ``telegram.Message`` usado por el servicio."""

    return SimpleNamespace(photo=photo, video=video, document=document)


def test_photo_uses_the_last_and_largest_telegram_resolution() -> None:
    small = SimpleNamespace(
        file_id="photo-small",
        file_unique_id="unique-small",
        file_size=1_024,
        width=90,
        height=60,
    )
    large = SimpleNamespace(
        file_id="photo-large",
        file_unique_id="unique-large",
        file_size=8_192,
        width=1_280,
        height=853,
    )

    result = telegram_media.extract_media_data(_message(photo=(small, large)))

    assert result is not None
    assert result.media_type is MediaType.PHOTO
    assert result.telegram_message_type is TelegramMessageType.PHOTO
    assert result.file_id == "photo-large"
    assert result.file_unique_id == "unique-large"
    assert result.mime_type == "image/jpeg"
    assert (result.width, result.height) == (1_280, 853)
    assert result.original_file_name is None
    assert result.duration_seconds is None


@pytest.mark.parametrize("duration", [17, timedelta(seconds=17)])
def test_native_video_preserves_telegram_metadata(
    duration: int | timedelta,
) -> None:
    video = SimpleNamespace(
        file_id="video-id",
        file_unique_id="video-unique",
        file_size=5_000_000,
        mime_type="video/mp4",
        file_name="evidencia.mp4",
        width=1_920,
        height=1_080,
        duration=duration,
    )

    result = telegram_media.extract_media_data(_message(video=video))

    assert result is not None
    assert result.media_type is MediaType.VIDEO
    assert result.telegram_message_type is TelegramMessageType.VIDEO
    assert result.file_id == "video-id"
    assert result.file_size == 5_000_000
    assert result.mime_type == "video/mp4"
    assert result.original_file_name == "evidencia.mp4"
    assert (result.width, result.height, result.duration_seconds) == (1_920, 1_080, 17)


@pytest.mark.parametrize(
    ("mime_type", "expected_media_type"),
    [
        ("image/png", MediaType.PHOTO),
        ("IMAGE/WEBP", MediaType.PHOTO),
        ("video/quicktime", MediaType.VIDEO),
        ("VIDEO/MP4", MediaType.VIDEO),
    ],
)
def test_compatible_documents_are_classified_from_mime_type(
    mime_type: str,
    expected_media_type: MediaType,
) -> None:
    document = SimpleNamespace(
        file_id="document-id",
        file_unique_id="document-unique",
        file_size=42,
        mime_type=mime_type,
        file_name="nombre-no-ejecutable.bin",
    )

    result = telegram_media.extract_media_data(_message(document=document))

    assert result is not None
    assert result.media_type is expected_media_type
    assert result.telegram_message_type is TelegramMessageType.DOCUMENT
    assert result.file_id == "document-id"
    assert result.original_file_name == "nombre-no-ejecutable.bin"
    # Telegram no proporciona dimensiones/duración en un Document genérico.
    assert result.width is None
    assert result.height is None
    assert result.duration_seconds is None


@pytest.mark.parametrize("mime_type", [None, "", "application/pdf", "text/plain"])
def test_document_with_untrusted_or_unsupported_mime_is_rejected(
    mime_type: str | None,
) -> None:
    # Una extensión atractiva no debe saltarse la validación MIME.
    document = SimpleNamespace(
        file_id="unsafe-id",
        file_unique_id="unsafe-unique",
        file_size=100,
        mime_type=mime_type,
        file_name="supuestamente-una-foto.jpg",
    )

    assert telegram_media.extract_media_data(_message(document=document)) is None


def test_message_without_supported_media_returns_none() -> None:
    assert telegram_media.extract_media_data(_message()) is None


@pytest.mark.asyncio
async def test_send_report_media_reuses_file_ids_with_matching_bot_methods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id = uuid4()
    records = [
        {
            "telegram_message_type": "PHOTO",
            "telegram_file_id": "stored-photo-id",
            "caption": "Foto",
        },
        {
            "telegram_message_type": "VIDEO",
            "telegram_file_id": "stored-video-id",
            "caption": None,
        },
        {
            "telegram_message_type": "DOCUMENT",
            "telegram_file_id": "stored-document-id",
            "caption": "Documento",
        },
    ]
    list_media = AsyncMock(return_value=records)
    monkeypatch.setattr(telegram_media, "list_report_media", list_media)

    bot = SimpleNamespace(
        send_photo=AsyncMock(),
        send_video=AsyncMock(),
        send_document=AsyncMock(),
        get_file=AsyncMock(),
    )
    pool = object()
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"db_pool": pool}),
        bot=bot,
    )

    sent = await telegram_media.send_report_media(context, 987_654_321, report_id)

    assert sent == 3
    list_media.assert_awaited_once_with(pool, report_id)
    bot.send_photo.assert_awaited_once_with(
        chat_id=987_654_321,
        photo="stored-photo-id",
        caption="Foto",
    )
    bot.send_video.assert_awaited_once_with(
        chat_id=987_654_321,
        video="stored-video-id",
        caption=None,
    )
    bot.send_document.assert_awaited_once_with(
        chat_id=987_654_321,
        document="stored-document-id",
        caption="Documento",
    )
    # El reenvío directo no necesita URL ni descarga.
    bot.get_file.assert_not_awaited()
