"""Manejo global y seguro de excepciones no previstas."""

import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes


logger = logging.getLogger(__name__)


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Registra el detalle técnico y muestra al usuario un mensaje neutro.

    El traceback queda en los logs del servidor. Nunca se envían consultas SQL,
    credenciales, el token ni detalles internos a través de Telegram.
    """

    error = context.error
    logger.error(
        "Error no controlado al procesar una actualización de Telegram",
        exc_info=(type(error), error, error.__traceback__)
        if isinstance(error, BaseException)
        else None,
    )

    if not isinstance(update, Update) or update.effective_message is None:
        return

    try:
        await update.effective_message.reply_text(
            "Ocurrió un error inesperado al procesar tu solicitud. "
            "Intenta nuevamente o usa /iniciar para comenzar otro reporte."
        )
    except TelegramError:
        # El error original es el importante. Un chat eliminado o bloqueado no
        # debe provocar una segunda excepción dentro del manejador global.
        logger.warning(
            "No fue posible notificar al usuario acerca del error",
            exc_info=True,
        )


__all__ = ["error_handler"]
