"""Utilidades compartidas por los repositorios PostgreSQL.

Las funciones públicas aceptan tanto un ``Pool`` como una ``Connection``. Esto
permite usarlas normalmente desde los handlers con el pool compartido y, a la
vez, componer varias operaciones dentro de una misma transacción cuando haga
falta.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypeAlias, cast

from asyncpg import Connection, Pool


Database: TypeAlias = Pool | Connection


@asynccontextmanager
async def acquire_connection(database: Database) -> AsyncIterator[Connection]:
    """Entrega una conexión y la devuelve al pool al terminar.

    Si el llamador ya proporciona una conexión, no se adquiere otra. Esta
    propiedad es importante para que todas las consultas de una operación
    sensible compartan la misma transacción.
    """

    if isinstance(database, Connection):
        yield database
        return

    pool = cast(Pool, database)
    async with pool.acquire() as connection:
        yield connection


@asynccontextmanager
async def transaction(database: Database) -> AsyncIterator[Connection]:
    """Abre una transacción sobre un pool o una conexión existente.

    asyncpg convierte una transacción anidada en un *savepoint*, por lo que el
    helper sigue siendo seguro si un servicio superior ya abrió una.
    """

    async with acquire_connection(database) as connection:
        async with connection.transaction():
            yield connection


__all__ = ["Database", "acquire_connection", "transaction"]
