"""Punto de entrada para ejecutar Galápagos Previene mediante polling."""

from __future__ import annotations

import logging

from telegram import Update

from app.bot import build_application
from app.config import ConfigurationError, Settings


def configure_logging(level: str) -> None:
    """Configura un formato uniforme sin mostrar tokens ni credenciales."""

    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        level=getattr(logging, level, logging.INFO),
    )
    # Las peticiones HTTP de Telegram son demasiado verbosas en nivel INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    """Valida el entorno, crea la aplicación y comienza el polling."""

    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        raise SystemExit(f"Error de configuración: {exc}") from exc

    configure_logging(settings.log_level)
    application = build_application(settings)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
