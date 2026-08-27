"""Carga y validación de la configuración del proyecto.

Los secretos se leen del entorno (o de un archivo ``.env`` local) y nunca se
escriben en el código fuente. Mantener esta lectura en un único módulo evita
que cada handler tenga que conocer nombres de variables de entorno.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Límite inicial solicitado. También puede modificarse con MAX_MEDIA_FILES sin
# cambiar código, por ejemplo al desplegar el bot en otra organización.
MAX_MEDIA_FILES = 10

# Raíz del repositorio, usada para resolver rutas relativas del entorno.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Video del tutorial que produce Remotion. `video/out/` no se versiona ni entra
# en la imagen de Docker, así que esta ruta solo existe al ejecutar el bot desde
# una copia del repositorio con el render hecho.
#
# Se envía el render de compatibilidad, no el máster 4K. El 4K de Remotion sale
# en H.264 nivel 5.2 y el reproductor integrado de Telegram no lo decodifica:
# ofrece abrirlo con una aplicación externa, lo que en la práctica significa que
# el tutorial no se ve. El nivel 4.2 de este archivo sí es universal.
DEFAULT_TUTORIAL_VIDEO_PATH = (
    PROJECT_ROOT / "video" / "out" / "flujo-telegram-1080p60.mp4"
)


class ConfigurationError(RuntimeError):
    """Indica que falta una variable o que su valor no es válido."""


def _positive_int(name: str, default: int) -> int:
    """Lee un entero positivo del entorno y produce un error comprensible."""

    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} debe ser un número entero.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} debe ser mayor que cero.")
    return value


def _tutorial_video_path() -> Path | None:
    """Resuelve el archivo de video con el que responde ``/tutorial``.

    Una ruta escrita a mano debe existir: si está mal, es preferible detener el
    arranque a descubrirlo cuando alguien pida el tutorial. La predeterminada,
    en cambio, falta por diseño en producción, y allí su ausencia solo significa
    que el comando responderá con el texto de ayuda.
    """

    raw_value = os.getenv("TUTORIAL_VIDEO_PATH", "").strip()
    if not raw_value:
        if DEFAULT_TUTORIAL_VIDEO_PATH.is_file():
            return DEFAULT_TUTORIAL_VIDEO_PATH
        return None

    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.is_file():
        raise ConfigurationError(
            f"TUTORIAL_VIDEO_PATH no apunta a un archivo existente: {path}"
        )
    return path


@dataclass(frozen=True, slots=True)
class Settings:
    """Valores de configuración ya validados y listos para usar."""

    telegram_bot_token: str
    database_url: str
    max_media_files: int = MAX_MEDIA_FILES
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    db_command_timeout: int = 30
    log_level: str = "INFO"
    # Fuentes del video del tutorial, en orden de preferencia. El file_id evita
    # subir los bytes en cada despliegue; la ruta sirve para el primer envío.
    tutorial_video_file_id: str | None = None
    tutorial_video_path: Path | None = None

    @classmethod
    def from_env(cls, env_file: str | Path | None = ".env") -> "Settings":
        """Construye la configuración a partir del entorno.

        ``override=False`` conserva variables definidas por systemd, Docker o la
        terminal; el archivo ``.env`` funciona únicamente como ayuda local.
        """

        if env_file is not None:
            load_dotenv(dotenv_path=env_file, override=False)

        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not token:
            raise ConfigurationError(
                "Falta TELEGRAM_BOT_TOKEN. Copia .env.example a .env y añade "
                "el token entregado por BotFather."
            )
        if not database_url:
            raise ConfigurationError(
                "Falta DATABASE_URL. Configura la conexión PostgreSQL en .env."
            )
        if not database_url.startswith(("postgresql://", "postgres://")):
            raise ConfigurationError(
                "DATABASE_URL debe comenzar con postgresql:// o postgres://."
            )

        min_size = _positive_int("DB_POOL_MIN_SIZE", 1)
        max_size = _positive_int("DB_POOL_MAX_SIZE", 10)
        if min_size > max_size:
            raise ConfigurationError(
                "DB_POOL_MIN_SIZE no puede ser mayor que DB_POOL_MAX_SIZE."
            )

        return cls(
            telegram_bot_token=token,
            database_url=database_url,
            max_media_files=_positive_int("MAX_MEDIA_FILES", MAX_MEDIA_FILES),
            db_pool_min_size=min_size,
            db_pool_max_size=max_size,
            db_command_timeout=_positive_int("DB_COMMAND_TIMEOUT", 30),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
            tutorial_video_file_id=os.getenv("TUTORIAL_VIDEO_FILE_ID", "").strip()
            or None,
            tutorial_video_path=_tutorial_video_path(),
        )
