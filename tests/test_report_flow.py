"""Pruebas del enrutamiento y de transiciones representativas del reporte."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from telegram.ext import CommandHandler, ConversationHandler

from app.handlers import report_flow
from app.models import ReportKind, WorkflowStep
from app.states import (
    ACTIVE_REPORT_ID_KEY,
    CHOOSE_EVENT_TYPE,
    CHOOSE_KIND,
    DB_USER_ID_KEY,
    WAITING_DESCRIPTION,
    WAITING_LOCATION,
    WAITING_MEDIA,
)


def _context(*, report_id: object | None = None) -> SimpleNamespace:
    user_data: dict[str, object] = {DB_USER_ID_KEY: uuid4()}
    if report_id is not None:
        user_data[ACTIVE_REPORT_ID_KEY] = report_id
    return SimpleNamespace(
        user_data=user_data,
        application=SimpleNamespace(bot_data={"db_pool": object()}),
    )


def _callback_update(data: str) -> tuple[SimpleNamespace, SimpleNamespace]:
    source_message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(
        data=data,
        message=source_message,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_chat=SimpleNamespace(id=123_456_789),
        effective_message=source_message,
    )
    return update, query


def _commands(handlers: list[object]) -> set[str]:
    result: set[str] = set()
    for handler in handlers:
        if isinstance(handler, CommandHandler):
            result.update(handler.commands)
    return result


def test_conversation_handler_exposes_the_expected_spanish_flow() -> None:
    handler = report_flow.build_conversation_handler()

    assert isinstance(handler, ConversationHandler)
    assert _commands(handler.entry_points) == {"start", "iniciar", "nuevo"}
    assert set(handler.states) == {
        CHOOSE_KIND,
        CHOOSE_EVENT_TYPE,
        WAITING_MEDIA,
        WAITING_LOCATION,
        WAITING_DESCRIPTION,
    }
    assert _commands(handler.fallbacks) == {"cancelar", "tutorial"}
    assert handler.allow_reentry is True
    assert handler.per_chat is True
    assert handler.per_user is True


@pytest.mark.asyncio
async def test_choose_event_creates_draft_then_requests_event_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id = uuid4()
    create_draft = AsyncMock(return_value=report_id)
    monkeypatch.setattr(report_flow, "create_draft", create_draft)
    context = _context()
    update, query = _callback_update("kind:EVENT")

    next_state = await report_flow.choose_kind(update, context)

    assert next_state == CHOOSE_EVENT_TYPE
    assert context.user_data[ACTIVE_REPORT_ID_KEY] == report_id
    create_draft.assert_awaited_once_with(
        context.application.bot_data["db_pool"],
        context.user_data[DB_USER_ID_KEY],
        123_456_789,
        ReportKind.EVENT,
        WorkflowStep.CHOOSE_EVENT_TYPE,
    )
    query.edit_message_text.assert_awaited_once()
    assert "tipo de evento" in query.edit_message_text.await_args.args[0].lower()
    query.message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_choose_incident_skips_event_type_and_requests_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id = uuid4()
    create_draft = AsyncMock(return_value=report_id)
    monkeypatch.setattr(report_flow, "create_draft", create_draft)
    context = _context()
    update, query = _callback_update("kind:INCIDENT")

    next_state = await report_flow.choose_kind(update, context)

    assert next_state == WAITING_MEDIA
    create_draft.assert_awaited_once_with(
        context.application.bot_data["db_pool"],
        context.user_data[DB_USER_ID_KEY],
        123_456_789,
        ReportKind.INCIDENT,
        WorkflowStep.WAITING_MEDIA,
    )
    assert "incidente" in query.edit_message_text.await_args.args[0].lower()
    assert "juntos" in query.edit_message_text.await_args.args[0].lower()


def _media_update(media_group_id: str | None = None) -> tuple[Any, Any]:
    """Construye un update de foto equivalente al que entrega Telegram."""

    message = SimpleNamespace(
        message_id=99,
        media_group_id=media_group_id,
        caption=None,
        reply_text=AsyncMock(),
    )
    return SimpleNamespace(effective_message=message, callback_query=None), message


@pytest.mark.asyncio
async def test_single_photo_closes_upload_and_requests_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id = uuid4()
    monkeypatch.setattr(
        report_flow,
        "extract_media_data",
        lambda message: SimpleNamespace(
            media_type="PHOTO",
            telegram_message_type="PHOTO",
            file_id="f",
            file_unique_id="u",
            mime_type=None,
            original_file_name=None,
            file_size=10,
            width=1,
            height=1,
            duration_seconds=None,
        ),
    )
    monkeypatch.setattr(report_flow, "create_report_media", AsyncMock(return_value=True))
    finalize = AsyncMock(return_value=1)
    monkeypatch.setattr(report_flow, "finalize_media_step", finalize)
    context = _context(report_id=report_id)
    update, message = _media_update()

    next_state = await report_flow.receive_media(update, context)

    assert next_state == WAITING_MEDIA
    finalize.assert_awaited_once()
    assert context.user_data[report_flow.MEDIA_CLOSED_KEY] is True
    # Un único mensaje: confirmación de la carga y solicitud de ubicación.
    message.reply_text.assert_awaited_once()
    texto = message.reply_text.await_args.args[0]
    assert "1 archivo(s)" in texto
    assert "ubicación" in texto


@pytest.mark.asyncio
async def test_media_after_upload_closed_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create = AsyncMock()
    monkeypatch.setattr(report_flow, "create_report_media", create)
    context = _context(report_id=uuid4())
    context.user_data[report_flow.MEDIA_CLOSED_KEY] = True
    update, message = _media_update()

    next_state = await report_flow.receive_media(update, context)

    assert next_state == WAITING_MEDIA
    create.assert_not_awaited()
    assert "ubicación" in message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_album_waits_for_remaining_items_before_closing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(report_flow, "MEDIA_GROUP_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(
        report_flow,
        "extract_media_data",
        lambda message: SimpleNamespace(
            media_type="PHOTO",
            telegram_message_type="PHOTO",
            file_id="f",
            file_unique_id="u",
            mime_type=None,
            original_file_name=None,
            file_size=10,
            width=1,
            height=1,
            duration_seconds=None,
        ),
    )
    monkeypatch.setattr(report_flow, "create_report_media", AsyncMock(return_value=True))
    finalize = AsyncMock(return_value=3)
    monkeypatch.setattr(report_flow, "finalize_media_step", finalize)
    context = _context(report_id=uuid4())

    for _ in range(3):
        update, message = _media_update(media_group_id="album-1")
        await report_flow.receive_media(update, context)
        # Ningún elemento del álbum confirma por separado.
        message.reply_text.assert_not_awaited()
        finalize.assert_not_awaited()

    await asyncio.sleep(0.2)

    finalize.assert_awaited_once()
    assert "3 archivo(s)" in message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_valid_description_submits_report_and_clears_temporary_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id = uuid4()
    submit = AsyncMock(return_value=SimpleNamespace(id=report_id))
    monkeypatch.setattr(report_flow, "submit_report", submit)

    message = SimpleNamespace(
        text="  Se observa fuego junto al camino.  ",
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_message=message,
        callback_query=None,
    )
    context = _context(report_id=report_id)
    pool = context.application.bot_data["db_pool"]

    next_state = await report_flow.receive_description(update, context)

    assert next_state == ConversationHandler.END
    submit.assert_awaited_once_with(
        pool,
        report_id,
        "Se observa fuego junto al camino.",
    )
    assert context.user_data == {}
    confirmation = message.reply_text.await_args.args[0]
    assert "reporte fue enviado" in confirmation
    assert "En caso de emergencia, llama al ECU 911." in confirmation
    # El código interno del reporte ya no se muestra al usuario.
    assert str(report_id).replace("-", "")[:8].upper() not in confirmation
