"""Pruebas del comando /tutorial y de la selección de la fuente del video."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import BadRequest

from app.handlers import commands
from app.handlers.commands import HELP_TEXT, TUTORIAL_FILE_ID_KEY, tutorial


def _update() -> tuple[SimpleNamespace, SimpleNamespace]:
    message = SimpleNamespace(reply_text=AsyncMock(), reply_video=AsyncMock())
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(id=123_456_789),
    )
    return update, message


def _context(**settings: object) -> SimpleNamespace:
    return SimpleNamespace(
        user_data={},
        bot=SimpleNamespace(send_chat_action=AsyncMock()),
        application=SimpleNamespace(bot_data={"settings": SimpleNamespace(**settings)}),
    )


def _sent_video(file_id: str) -> SimpleNamespace:
    return SimpleNamespace(video=SimpleNamespace(file_id=file_id))


async def test_tutorial_reenvia_el_file_id_configurado_sin_subir_el_archivo() -> None:
    context = _context(
        tutorial_video_file_id="BAACAgEAAx0",
        tutorial_video_path=Path("/no/se/usa.mp4"),
    )
    update, message = _update()
    message.reply_video.return_value = _sent_video("BAACAgEAAx0")

    await tutorial(update, context)

    message.reply_video.assert_awaited_once()
    kwargs = message.reply_video.await_args.kwargs
    assert kwargs["video"] == "BAACAgEAAx0"
    assert kwargs["caption"] == HELP_TEXT
    # Un file_id no viaja por la red: no hace falta avisar de una subida.
    context.bot.send_chat_action.assert_not_awaited()
    message.reply_text.assert_not_awaited()


async def test_tutorial_sube_el_archivo_local_y_cachea_el_file_id(
    tmp_path: Path,
) -> None:
    video = tmp_path / "flujo-telegram.mp4"
    video.write_bytes(b"mp4")
    context = _context(tutorial_video_file_id=None, tutorial_video_path=video)
    update, message = _update()
    message.reply_video.return_value = _sent_video("FILE_ID_NUEVO")

    await tutorial(update, context)

    kwargs = message.reply_video.await_args.kwargs
    assert kwargs["video"] == video
    assert kwargs["supports_streaming"] is True
    context.bot.send_chat_action.assert_awaited_once()
    assert context.application.bot_data[TUTORIAL_FILE_ID_KEY] == "FILE_ID_NUEVO"

    # El segundo /tutorial ya reutiliza el identificador cacheado.
    update, message = _update()
    message.reply_video.return_value = _sent_video("FILE_ID_NUEVO")
    await tutorial(update, context)

    assert message.reply_video.await_args.kwargs["video"] == "FILE_ID_NUEVO"


async def test_tutorial_responde_con_texto_cuando_no_hay_video() -> None:
    context = _context(tutorial_video_file_id=None, tutorial_video_path=None)
    update, message = _update()

    await tutorial(update, context)

    message.reply_video.assert_not_awaited()
    message.reply_text.assert_awaited_once_with(HELP_TEXT)


async def test_tutorial_recurre_al_texto_si_telegram_rechaza_el_video() -> None:
    context = _context(tutorial_video_file_id="FILE_ID_INVALIDO")
    update, message = _update()
    message.reply_video.side_effect = BadRequest("wrong file identifier")

    await tutorial(update, context)

    message.reply_text.assert_awaited_once_with(HELP_TEXT)
    assert TUTORIAL_FILE_ID_KEY not in context.application.bot_data


async def test_tutorial_no_cachea_cuando_telegram_lo_guarda_como_documento(
    tmp_path: Path,
) -> None:
    video = tmp_path / "flujo-telegram.mp4"
    video.write_bytes(b"mp4")
    context = _context(tutorial_video_file_id=None, tutorial_video_path=video)
    update, message = _update()
    message.reply_video.return_value = SimpleNamespace(video=None)

    await tutorial(update, context)

    assert TUTORIAL_FILE_ID_KEY not in context.application.bot_data


def test_el_texto_de_ayuda_cabe_en_un_pie_de_foto_de_telegram() -> None:
    # Telegram corta las descripciones de más de 1024 caracteres.
    assert len(commands.HELP_TEXT) <= 1024


async def test_tutorial_registra_el_file_id_nuevo_una_sola_vez(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    video = tmp_path / "flujo-telegram-4k60.mp4"
    video.write_bytes(b"mp4")
    context = _context(tutorial_video_file_id=None, tutorial_video_path=video)
    update, message = _update()
    message.reply_video.return_value = _sent_video("FILE_ID_REGISTRADO")

    with caplog.at_level("INFO", logger=commands.logger.name):
        await tutorial(update, context)
        # El segundo envío reutiliza el mismo identificador: no vuelve a avisar.
        update, message = _update()
        message.reply_video.return_value = _sent_video("FILE_ID_REGISTRADO")
        await tutorial(update, context)

    avisos = [r for r in caplog.records if "TUTORIAL_VIDEO_FILE_ID" in r.getMessage()]
    assert len(avisos) == 1
    assert "FILE_ID_REGISTRADO" in avisos[0].getMessage()
