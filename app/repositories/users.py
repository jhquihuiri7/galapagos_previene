"""Persistencia de usuarios de Telegram.

Telegram es la fuente de los datos de perfil. El *upsert* conserva el UUID
interno y actualiza los campos que el usuario puede cambiar (por ejemplo, su
nombre de usuario) cada vez que inicia un flujo.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4

from asyncpg import Record

from app.repositories import Database, acquire_connection


class TelegramUserLike(Protocol):
    """Subconjunto de ``telegram.User`` que necesita este repositorio."""

    id: int
    username: str | None
    first_name: str
    last_name: str | None
    language_code: str | None


def _optional_text(value: object, field_name: str, max_length: int) -> str | None:
    """Normaliza texto opcional sin truncar silenciosamente datos."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} debe ser texto o None")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise ValueError(
            f"{field_name} supera el máximo permitido de {max_length} caracteres"
        )
    return normalized


def _telegram_user_id(value: object) -> int:
    """Valida que el identificador quepa en un ``BIGINT`` de PostgreSQL."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("telegram_user.id debe ser un número entero")
    if value <= 0:
        raise ValueError("telegram_user.id debe ser mayor que cero")
    if value > 9_223_372_036_854_775_807:
        raise ValueError("telegram_user.id excede la capacidad de BIGINT")
    return value


async def upsert_telegram_user(
    database: Database,
    telegram_user: TelegramUserLike,
) -> UUID:
    """Crea o actualiza un usuario y devuelve su UUID interno.

    La consulta está parametrizada: ningún dato recibido desde Telegram se
    concatena al SQL. Ante conflicto por ``telegram_user_id`` se mantiene el
    UUID ya existente, preservando así todos sus reportes relacionados.
    """

    telegram_user_id = _telegram_user_id(telegram_user.id)
    username = _optional_text(telegram_user.username, "username", 64)
    first_name = _optional_text(telegram_user.first_name, "first_name", 128)
    last_name = _optional_text(telegram_user.last_name, "last_name", 128)
    language_code = _optional_text(
        telegram_user.language_code,
        "language_code",
        16,
    )

    new_id = uuid4()
    query = """
        INSERT INTO telegram_users (
            id,
            telegram_user_id,
            username,
            first_name,
            last_name,
            language_code
        )
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (telegram_user_id) DO UPDATE
        SET
            username = EXCLUDED.username,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            language_code = EXCLUDED.language_code,
            updated_at = NOW()
        RETURNING id
    """

    async with acquire_connection(database) as connection:
        user_id = await connection.fetchval(
            query,
            new_id,
            telegram_user_id,
            username,
            first_name,
            last_name,
            language_code,
        )

    if user_id is None:  # Defensa: INSERT ... RETURNING siempre debe responder.
        raise RuntimeError("PostgreSQL no devolvió el UUID del usuario")
    return user_id if isinstance(user_id, UUID) else UUID(str(user_id))


async def get_user_by_telegram_id(
    database: Database,
    telegram_user_id: int,
) -> Record | None:
    """Obtiene la fila completa de un usuario por su identificador Telegram."""

    normalized_id = _telegram_user_id(telegram_user_id)
    async with acquire_connection(database) as connection:
        return await connection.fetchrow(
            """
            SELECT
                id,
                telegram_user_id,
                username,
                first_name,
                last_name,
                language_code,
                created_at,
                updated_at
            FROM telegram_users
            WHERE telegram_user_id = $1
            """,
            normalized_id,
        )


async def get_user_id_by_telegram_id(
    database: Database,
    telegram_user_id: int,
) -> UUID | None:
    """Devuelve solo el UUID interno cuando no se necesita el perfil."""

    normalized_id = _telegram_user_id(telegram_user_id)
    async with acquire_connection(database) as connection:
        user_id = await connection.fetchval(
            "SELECT id FROM telegram_users WHERE telegram_user_id = $1",
            normalized_id,
        )
    if user_id is None:
        return None
    return user_id if isinstance(user_id, UUID) else UUID(str(user_id))


__all__ = [
    "TelegramUserLike",
    "get_user_by_telegram_id",
    "get_user_id_by_telegram_id",
    "upsert_telegram_user",
]
