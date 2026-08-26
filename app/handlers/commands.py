"""Comandos generales de Galápagos Previene."""

import logging
from typing import Any
from uuid import UUID

from telegram import Update
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


__all__ = ["HELP_TEXT", "cancel", "help_command", "start"]
