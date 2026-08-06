"""Configuración del servicio HTTP de lectura.

Se mantiene aparte de :class:`app.config.Settings` porque los dos procesos
necesitan cosas distintas: el bot no debe exigir una API key y la API no debe
poder arrancar con credenciales de escritura por descuido. Compartir un único
objeto obligaría a que cada servicio tolerase variables que no le competen.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.config import ConfigurationError, _positive_int


# Una clave corta es adivinable por fuerza bruta aunque la comparación sea
# constante. 32 caracteres equivalen a los 24 bytes de `secrets.token_urlsafe`.
MIN_API_KEY_LENGTH = 32


@dataclass(frozen=True, slots=True)
class ApiSettings:
    """Valores validados que necesita el servicio REST."""

    database_url: str
    api_keys: frozenset[str]
    telegram_bot_token: str
    media_chunk_size: int = 64 * 1024
    media_timeout_seconds: int = 60
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    db_command_timeout: int = 30
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env_file: str | Path | None = ".env") -> "ApiSettings":
        """Construye la configuración de la API a partir del entorno."""

        if env_file is not None:
            load_dotenv(dotenv_path=env_file, override=False)

        database_url = os.getenv("API_DATABASE_URL", "").strip()
        if not database_url:
            raise ConfigurationError(
                "Falta API_DATABASE_URL. Debe apuntar al rol de solo lectura "
                "creado con sql/api_readonly.sql, no al usuario del bot."
            )
        if not database_url.startswith(("postgresql://", "postgres://")):
            raise ConfigurationError(
                "API_DATABASE_URL debe comenzar con postgresql:// o postgres://."
            )

        # Varias claves permiten rotarlas sin cortar el servicio: se añade la
        # nueva, se migra a SIGTAR y luego se retira la anterior.
        raw_keys = os.getenv("API_KEYS", "")
        api_keys = frozenset(
            key.strip() for key in raw_keys.split(",") if key.strip()
        )
        if not api_keys:
            raise ConfigurationError(
                "Falta API_KEYS. Genera una clave con "
                "`python -c \"import secrets; print(secrets.token_urlsafe(32))\"`."
            )
        short_keys = [key for key in api_keys if len(key) < MIN_API_KEY_LENGTH]
        if short_keys:
            raise ConfigurationError(
                f"Cada valor de API_KEYS debe tener al menos "
                f"{MIN_API_KEY_LENGTH} caracteres."
            )

        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ConfigurationError(
                "Falta TELEGRAM_BOT_TOKEN. La API lo necesita para descargar "
                "las evidencias alojadas en Telegram."
            )

        min_size = _positive_int("API_DB_POOL_MIN_SIZE", 1)
        max_size = _positive_int("API_DB_POOL_MAX_SIZE", 10)
        if min_size > max_size:
            raise ConfigurationError(
                "API_DB_POOL_MIN_SIZE no puede ser mayor que API_DB_POOL_MAX_SIZE."
            )

        return cls(
            database_url=database_url,
            api_keys=api_keys,
            telegram_bot_token=token,
            media_chunk_size=_positive_int("API_MEDIA_CHUNK_SIZE", 64 * 1024),
            media_timeout_seconds=_positive_int("API_MEDIA_TIMEOUT_SECONDS", 60),
            db_pool_min_size=min_size,
            db_pool_max_size=max_size,
            db_command_timeout=_positive_int("API_DB_COMMAND_TIMEOUT", 30),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        )


__all__ = ["ApiSettings", "MIN_API_KEY_LENGTH"]
