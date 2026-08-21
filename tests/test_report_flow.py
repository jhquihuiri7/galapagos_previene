"""Pruebas del enrutamiento y de transiciones representativas del reporte."""

from __future__ import annotations

from types import SimpleNamespace
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
    assert _commands(handler.fallbacks) == {"cancelar", "ayuda"}
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
    query.message.reply_text.assert_awaited_once()
    assert "cuando termines" in query.message.reply_text.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_finish_media_without_evidence_shows_alert_and_stays_in_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id = uuid4()
    finalize = AsyncMock(side_effect=report_flow.NoMediaFilesError())
    monkeypatch.setattr(report_flow, "finalize_media_step", finalize)
    context = _context(report_id=report_id)
    update, query = _callback_update("media:finish")

    next_state = await report_flow.finish_media(update, context)

    assert next_state == WAITING_MEDIA
    finalize.assert_awaited_once_with(
        context.application.bot_data["db_pool"],
        report_id,
    )
    query.answer.assert_awaited_once_with(
        "Envíame al menos una foto o video antes de continuar.",
        show_alert=True,
    )
    query.edit_message_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_description_submits_report_and_clears_temporary_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id = uuid4()
    submit = AsyncMock(return_value=SimpleNamespace(id=report_id))
    count_media = AsyncMock(return_value=3)
    monkeypatch.setattr(report_flow, "submit_report", submit)
    monkeypatch.setattr(report_flow, "count_report_media", count_media)

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
    assert "911" in confirmation
    # El código interno del reporte ya no se muestra al usuario.
    assert str(report_id).replace("-", "")[:8].upper() not in confirmation
