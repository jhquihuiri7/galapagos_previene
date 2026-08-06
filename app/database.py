"""Creación, inicialización y cierre del pool de PostgreSQL.

La aplicación crea un único :class:`asyncpg.Pool` al arrancar y lo comparte a
través de ``application.bot_data["db_pool"]``. Cada repositorio toma del pool
una conexión solo durante el tiempo que dura su operación.
"""

from __future__ import annotations

from pathlib import Path

import asyncpg
from asyncpg import Pool


DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


async def create_pool(
    database_url: str,
    min_size: int = 1,
    max_size: int = 10,
    command_timeout: float = 30,
) -> Pool:
    """Crea el pool compartido usando los valores seguros del proyecto.

    Args:
        database_url: DSN de PostgreSQL, leído normalmente de ``DATABASE_URL``.
        min_size: Cantidad mínima de conexiones mantenidas abiertas.
        max_size: Límite de conexiones simultáneas del proceso.
        command_timeout: Tiempo máximo, en segundos, para una consulta.

    Raises:
        ValueError: Si la configuración básica del pool no es coherente.
        asyncpg.PostgresError: Si PostgreSQL rechaza la conexión.
    """

    database_url = database_url.strip()
    if not database_url:
        raise ValueError("database_url no puede estar vacía")
    if min_size < 0:
        raise ValueError("min_size no puede ser negativo")
    if max_size <= 0:
        raise ValueError("max_size debe ser mayor que cero")
    if min_size > max_size:
        raise ValueError("min_size no puede ser mayor que max_size")
    if command_timeout <= 0:
        raise ValueError("command_timeout debe ser mayor que cero")

    # El DSN se pasa como parámetro; nunca se concatena con una consulta SQL.
    return await asyncpg.create_pool(
        database_url,
        min_size=min_size,
        max_size=max_size,
        command_timeout=command_timeout,
    )


async def initialize_database(
    pool: Pool,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
) -> None:
    """Ejecuta ``schema.sql`` dentro de una transacción.

    El esquema usa ``IF NOT EXISTS`` y un *upsert* para el catálogo de eventos,
    por lo que este procedimiento se puede repetir en cada arranque. Si una
    sentencia falla, PostgreSQL revierte toda la inicialización.
    """

    path = Path(schema_path).expanduser().resolve()
    schema_sql = path.read_text(encoding="utf-8")
    if not schema_sql.strip():
        raise ValueError(f"El archivo de esquema está vacío: {path}")

    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(schema_sql)


async def close_pool(pool: Pool | None) -> None:
    """Cierra ordenadamente todas las conexiones del pool.

    Aceptar ``None`` simplifica el apagado si el arranque falló antes de crear
    la conexión. ``Pool.close`` espera a que se devuelvan conexiones prestadas.
    """

    if pool is not None:
        await pool.close()


__all__ = [
    "DEFAULT_SCHEMA_PATH",
    "close_pool",
    "create_pool",
    "initialize_database",
]
