"""Comandos generales de Galápagos Previene."""

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from telegram import Message, Update
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import ContextTypes, ConversationHandler

from app.keyboards import remove_keyboard, report_kind_keyboard
from app.repositories.reports import cancel_active_draft
from app.repositories.users import upsert_telegram_user
from app.states import CHOOSE_KIND, DB_USER_ID_KEY


logger = logging.getLogger(__name__)


HELP_TEXT = """🤖 Galápagos Previene

Reportar es fácil, solo 4 pasos:
1️⃣ Elige qué pasó
2️⃣ Envía fotos o videos
3️⃣ Comparte tu ubicación
4️⃣ Cuéntanos brevemente

Comandos:
/iniciar - Nuevo reporte
/nuevo - Registrar otro reporte
/cancelar - Cancelar el reporte actual
/tutorial - Ver el tutorial

🚨 Si es una emergencia, llama al 911."""

# La primera subida mueve decenas de megabytes y tarda mucho más que una
# petición normal de la API de Telegram.
TUTORIAL_UPLOAD_TIMEOUT_SECONDS = 300.0

# Telegram devuelve un file_id reutilizable después de aceptar el archivo.
# Guardarlo en bot_data evita volver a subir los bytes en cada /tutorial.
TUTORIAL_FILE_ID_KEY = "tutorial_video_file_id"


def _pool(context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Obtiene el pool inicializado por ``app.bot`` con un error explicativo."""

    try:
        return context.application.bot_data["db_pool"]
    except KeyError as exc:  # pragma: no cover - indica una mala configuración al arrancar
        raise RuntimeError("El pool de PostgreSQL no está inicializado") from exc


async def _database_user_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> UUID:
    """Actualiza los datos del usuario de Telegram y conserva su UUID interno."""

    telegram_user = update.effective_user
    if telegram_user is None:
        raise ValueError("La actualización no contiene un usuario de Telegram")

    user_id = await upsert_telegram_user(_pool(context), telegram_user)
    context.user_data[DB_USER_ID_KEY] = user_id
    return user_id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el mismo flujo para ``/start``, ``/iniciar`` y ``/nuevo``.

    Por decisión de producto, comenzar de nuevo cancela automáticamente el
    borrador anterior. No se elimina: queda auditado como ``CANCELLED``.
    """

    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None or update.effective_user is None:
        logger.warning("Se recibió un comando de inicio sin usuario, chat o mensaje")
        return ConversationHandler.END

    # Se limpia primero cualquier estado en memoria; el UUID del usuario se
    # vuelve a guardar inmediatamente después de sincronizarlo con PostgreSQL.
    context.user_data.clear()
    user_id = await _database_user_id(update, context)
    cancelled = await cancel_active_draft(_pool(context), user_id)

    if cancelled:
        await message.reply_text(
            "El borrador anterior fue cancelado.",
            reply_markup=remove_keyboard(),
        )
    await message.reply_text(
        "🌿 ¡Hola! Bienvenido a Galápagos Previene.\n\n"
        "Aquí puedes avisarnos de algo que esté pasando en las islas.\n\n"
        "¿Qué quieres reportar?",
        reply_markup=report_kind_keyboard(),
    )
    return CHOOSE_KIND


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela de forma lógica el borrador activo y termina la conversación."""

    message = update.effective_message
    if update.effective_user is None:
        return ConversationHandler.END

    user_id = context.user_data.get(DB_USER_ID_KEY)
    if user_id is None:
        user_id = await _database_user_id(update, context)

    cancelled = await cancel_active_draft(_pool(context), user_id)
    context.user_data.clear()

    if message is not None:
        if cancelled:
            text = (
                "✅ Cancelado. No enviamos nada.\n\n"
                "Cuando quieras, escribe /nuevo."
            )
        else:
            text = (
                "No tienes ningún reporte en curso. "
                "Escribe /iniciar para empezar."
            )
        await message.reply_text(text, reply_markup=remove_keyboard())

    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra instrucciones sin modificar el estado actual de la conversación."""

    del context  # El comando no necesita datos de sesión ni de PostgreSQL.
    if update.effective_message is not None:
        await update.effective_message.reply_text(HELP_TEXT)


def _tutorial_source(context: ContextTypes.DEFAULT_TYPE) -> str | Path | None:
    """Elige de dónde sale el video, de lo más económico a lo más costoso.

    Un ``file_id`` ya conocido —configurado o cacheado tras la primera subida—
    se reenvía sin transferir bytes. La ruta local solo se usa cuando todavía no
    hay ninguno, y ``None`` significa que el comando responderá con texto.
    """

    bot_data = context.application.bot_data
    settings = bot_data.get("settings")

    configured_file_id = getattr(settings, "tutorial_video_file_id", None)
    if isinstance(configured_file_id, str) and configured_file_id:
        return configured_file_id

    cached_file_id = bot_data.get(TUTORIAL_FILE_ID_KEY)
    if isinstance(cached_file_id, str) and cached_file_id:
        return cached_file_id

    path = getattr(settings, "tutorial_video_path", None)
    return path if isinstance(path, Path) else None


def _remember_tutorial_file_id(
    context: ContextTypes.DEFAULT_TYPE,
    sent_message: Message | None,
    *,
    uploaded: bool,
) -> None:
    """Cachea el file_id del video enviado para no repetir la subida.

    El caché vive en memoria, así que se pierde al reiniciar el proceso. Por eso
    una subida real registra además el identificador: es lo que hay que copiar
    en ``TUTORIAL_VIDEO_FILE_ID`` para que no vuelva a ocurrir. No es un secreto
    —solo funciona con este bot, que ya guarda file_id de evidencias en
    PostgreSQL— a diferencia de las URL temporales de ``get_file()``.

    ``uploaded`` distingue esa situación de un simple reenvío. Sin ese dato el
    aviso saldría también en el primer /tutorial de cada arranque, cuando el
    identificador ya venía configurado y no se transfirió ningún byte.
    """

    bot_data = context.application.bot_data
    video = getattr(sent_message, "video", None)
    file_id = getattr(video, "file_id", None)
    if not isinstance(file_id, str) or not file_id:
        return
    if uploaded:
        logger.info(
            "Video del tutorial subido. Para no repetir la subida, configure "
            "TUTORIAL_VIDEO_FILE_ID=%s",
            file_id,
        )
    bot_data[TUTORIAL_FILE_ID_KEY] = file_id


async def tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía el video del flujo sin alterar el reporte que esté en curso.

    Si no hay video disponible —o Telegram lo rechaza— el comando conserva su
    comportamiento anterior y responde con las instrucciones en texto.
    """

    message = update.effective_message
    if message is None:
        return

    source = _tutorial_source(context)
    if source is None:
        await message.reply_text(HELP_TEXT)
        return

    uploaded = isinstance(source, Path)
    try:
        if uploaded:
            chat = update.effective_chat
            if chat is not None:
                # La subida inicial no es instantánea; el aviso evita que
                # parezca que el comando quedó sin respuesta.
                await context.bot.send_chat_action(
                    chat.id,
                    ChatAction.UPLOAD_VIDEO,
                )
            sent_message = await message.reply_video(
                video=source,
                caption=HELP_TEXT,
                supports_streaming=True,
                read_timeout=TUTORIAL_UPLOAD_TIMEOUT_SECONDS,
                write_timeout=TUTORIAL_UPLOAD_TIMEOUT_SECONDS,
            )
        else:
            sent_message = await message.reply_video(
                video=source,
                caption=HELP_TEXT,
                supports_streaming=True,
            )
    except TelegramError:
        logger.exception("No fue posible enviar el video del tutorial")
        await message.reply_text(HELP_TEXT)
        return

    _remember_tutorial_file_id(context, sent_message, uploaded=uploaded)


__all__ = [
    "HELP_TEXT",
    "TUTORIAL_FILE_ID_KEY",
    "cancel",
    "help_command",
    "start",
    "tutorial",
]
