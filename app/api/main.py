"""Servicio REST de solo lectura para consumidores externos (SIGTAR).

Corre como un proceso independiente del bot. Comparte el modelo de dominio y
los repositorios, pero se conecta a PostgreSQL con un rol sin permisos de
escritura, de modo que un fallo aquí no pueda alterar los reportes.

Arranque local:

    uvicorn --factory app.api.main:build_app --host 127.0.0.1 --port 8080
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import httpx
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from app.api.config import ApiSettings
from app.api.deps import PoolDep, require_api_key
from app.api.routers import media, reports
from app.api.schemas import HealthOut
from app.config import ConfigurationError
from app.database import close_pool, create_pool


logger = logging.getLogger(__name__)


def configure_logging(level: str) -> None:
    """Aplica el mismo formato que usa el bot, sin exponer credenciales."""

    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        level=getattr(logging, level, logging.INFO),
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Crea el pool y el cliente HTTP una vez, y los cierra al terminar.

    Reutilizar un único ``AsyncClient`` mantiene viva la conexión TLS con
    Telegram entre descargas; crear uno por petición añadiría un saludo TLS
    completo a cada archivo.
    """

    settings: ApiSettings = app.state.settings
    pool = None
    client = None
    try:
        pool = await create_pool(
            settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            command_timeout=settings.db_command_timeout,
        )
        # La API no ejecuta schema.sql: su rol no tiene permisos de DDL y el
        # esquema es responsabilidad exclusiva del bot.
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.media_timeout_seconds, connect=10.0),
            follow_redirects=False,
        )
        app.state.db_pool = pool
        app.state.http_client = client
        logger.info("API de lectura lista")
        yield
    finally:
        if client is not None:
            await client.aclose()
        await close_pool(pool)


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Construye la aplicación. Aceptar ``settings`` facilita las pruebas."""

    resolved = settings if settings is not None else ApiSettings.from_env()
    configure_logging(resolved.log_level)

    app = FastAPI(
        title="Galápagos Previene — API de reportes",
        version="1.0.0",
        summary="Lectura de reportes ciudadanos enviados por Telegram",
        lifespan=lifespan,
        # La documentación describe el contrato pero no debe ser anónima: se
        # protege igual que los datos, ya que revela la forma de los endpoints.
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.state.settings = resolved

    # La autenticación se declara en el router, no endpoint por endpoint: así
    # un endpoint nuevo nace protegido en lugar de nacer abierto.
    guarded = [Depends(require_api_key)]
    app.include_router(reports.router, dependencies=guarded)
    app.include_router(media.router, dependencies=guarded)

    @app.get("/healthz", response_model=HealthOut, tags=["operación"])
    async def healthz(pool: PoolDep) -> JSONResponse:
        """Comprueba que el proceso responde y que PostgreSQL contesta.

        Sin autenticación, porque lo consulta el healthcheck de Docker. No
        revela nada más que la disponibilidad del servicio.
        """

        try:
            await pool.fetchval("SELECT 1")
        except Exception:  # noqa: BLE001 - cualquier fallo es "no disponible"
            logger.exception("La comprobación de salud no pudo consultar la base")
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "database": "unreachable"},
            )
        return JSONResponse(content={"status": "ok", "database": "ok"})

    return app


def build_app() -> FastAPI:
    """Punto de entrada para uvicorn (``--factory app.api.main:build_app``).

    Se construye bajo demanda y no al importar el módulo. Importar no debe
    exigir un entorno completo: de lo contrario las pruebas no podrían cargar
    nada de este paquete sin definir antes todas las variables de producción.
    """

    try:
        return create_app()
    except ConfigurationError as exc:
        raise SystemExit(f"Error de configuración: {exc}") from exc


__all__ = ["build_app", "create_app"]
