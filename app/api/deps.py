"""Dependencias compartidas por los routers: estado, pool y autenticación."""

from __future__ import annotations

import secrets
from typing import Annotated

from asyncpg import Pool
from fastapi import Depends, Header, HTTPException, Request, status

from app.api.config import ApiSettings


def get_settings(request: Request) -> ApiSettings:
    """Recupera la configuración validada durante el arranque."""

    return request.app.state.settings


def get_pool(request: Request) -> Pool:
    """Recupera el pool de PostgreSQL creado en el ``lifespan``."""

    return request.app.state.db_pool


def require_api_key(
    settings: Annotated[ApiSettings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Valida la cabecera ``Authorization: Bearer <clave>``.

    La comparación usa :func:`secrets.compare_digest` contra cada clave
    configurada. Un ``==`` normal termina en cuanto encuentra el primer
    carácter distinto, y esa diferencia de tiempo permite reconstruir la clave
    carácter a carácter. Se recorren todas las claves sin cortar en la primera
    coincidencia por la misma razón.
    """

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta la cabecera Authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, candidate = authorization.partition(" ")
    if scheme.lower() != "bearer" or not candidate:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El formato esperado es 'Authorization: Bearer <clave>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    matched = False
    for key in settings.api_keys:
        if secrets.compare_digest(candidate, key):
            matched = True
    if not matched:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clave de API no válida",
            headers={"WWW-Authenticate": "Bearer"},
        )


PoolDep = Annotated[Pool, Depends(get_pool)]
SettingsDep = Annotated[ApiSettings, Depends(get_settings)]


__all__ = [
    "PoolDep",
    "SettingsDep",
    "get_pool",
    "get_settings",
    "require_api_key",
]
