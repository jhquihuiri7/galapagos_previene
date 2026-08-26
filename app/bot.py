"""Construcción y ciclo de vida de la aplicación de Telegram.

Este módulo concentra la infraestructura: abre PostgreSQL al iniciar, registra
los comandos visibles, instala los handlers y cierra el pool al detenerse. La
lógica del reporte permanece en ``app.handlers`` y no depende de polling, lo
que facilita cambiar más adelante a ``run_webhook``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

import asyncpg
from telegram import BotCommand
from telegram.ext import Application, CommandHandler

from app.config import Settings
from app.database import close_pool, create_pool, initialize_database
from app.handlers.commands import cancel, help_command
from app.handlers.errors import error_handler
from app.handlers.report_flow import build_conversation_handler

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "schema.sql"

BOT_COMMANDS = [
    BotCommand("iniciar", "Crear un reporte"),
    BotCommand("nuevo", "Reportar algo más"),
    BotCommand("cancelar", "Cancelar el reporte"),
    BotCommand("tutorial", "Ver tutorial"),
]


async def post_init(application: Application) -> None:
    """Prepara PostgreSQL y el menú de comandos antes de recibir updates."""

    settings = cast(Settings, application.bot_data["settings"])
    pool: asyncpg.Pool | None = None
    try:
        pool = await create_pool(
            settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            command_timeout=settings.db_command_timeout,
        )
        await initialize_database(pool, SCHEMA_PATH)
        await application.bot.set_my_commands(BOT_COMMANDS)
    except Exception:
        # Si el arranque queda a medias, no dejamos conexiones abiertas.
        if pool is not None:
            await close_pool(pool)
        logger.exception("No fue posible inicializar Galápagos Previene")
        raise

    application.bot_data["db_pool"] = pool
    logger.info("Base de datos preparada y comandos de Telegram configurados")


async def post_shutdown(application: Application) -> None:
    """Cierra limpiamente todas las conexiones al detener el proceso."""

    pool = application.bot_data.pop("db_pool", None)
    if pool is not None:
        await close_pool(pool)
        logger.info("Pool de PostgreSQL cerrado")


def build_application(settings: Settings) -> Application:
    """Crea la aplicación lista para ejecutarse con polling o webhook.

    ``concurrent_updates(False)`` es deliberado: ``ConversationHandler`` debe
    procesar en orden las respuestas de una misma conversación, especialmente
    los elementos separados que Telegram genera para un álbum.
    """

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .concurrent_updates(False)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data["settings"] = settings

    # Los handlers independientes están en el mismo grupo y después del
    # ConversationHandler. Así atienden /tutorial y /cancelar fuera de un flujo,
    # pero no se ejecutan dos veces cuando una conversación ya está activa.
    application.add_handler(build_conversation_handler())
    application.add_handler(CommandHandler("tutorial", help_command))
    application.add_handler(CommandHandler("cancelar", cancel))
    application.add_error_handler(error_handler)
    return application


__all__ = [
    "BOT_COMMANDS",
    "build_application",
    "post_init",
    "post_shutdown",
]
