"""Descarga de evidencias desde Telegram hacia el consumidor, sin disco.

Telegram no entrega una URL permanente: hay que pedir ``getFile`` para obtener
una ruta temporal y descargar desde ella usando el token del bot. Ese token es
la credencial que controla todo el bot, así que nunca sale de este proceso —
por eso la API actúa de intermediaria en lugar de publicar ``file_id`` o la URL
temporal.

Los bytes se retransmiten por trozos según llegan. El contenedor puede seguir
montándose en modo solo lectura porque nunca se escribe un archivo temporal, y
la memoria usada no depende del tamaño del video.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Final

import httpx


logger = logging.getLogger(__name__)

TELEGRAM_API_BASE: Final[str] = "https://api.telegram.org"


class TelegramFileError(RuntimeError):
    """Telegram no pudo entregar el archivo solicitado."""


class TelegramFileNotFoundError(TelegramFileError):
    """El ``file_id`` ya no es válido o el archivo expiró en Telegram."""


def _redact(message: str, token: str) -> str:
    """Elimina el token del texto antes de registrarlo o propagarlo.

    httpx incluye la URL completa en sus errores, y la URL de descarga lleva el
    token embebido. Sin esta limpieza, un fallo de red acabaría escribiendo la
    credencial del bot en los logs.
    """

    return message.replace(token, "***") if token else message


async def resolve_file_path(client: httpx.AsyncClient, token: str, file_id: str) -> str:
    """Traduce un ``file_id`` en la ruta temporal que sirve Telegram.

    Raises:
        TelegramFileNotFoundError: Si Telegram rechaza el identificador.
        TelegramFileError: Ante cualquier otro fallo de la API.
    """

    try:
        response = await client.get(
            f"{TELEGRAM_API_BASE}/bot{token}/getFile",
            params={"file_id": file_id},
        )
    except httpx.HTTPError as exc:
        raise TelegramFileError(
            _redact(f"No se pudo contactar con Telegram: {exc}", token)
        ) from exc

    if response.status_code in (400, 404):
        raise TelegramFileNotFoundError(
            "Telegram no reconoce el archivo; puede haber expirado"
        )
    if response.status_code != 200:
        raise TelegramFileError(
            f"Telegram respondió con el estado {response.status_code}"
        )

    payload = response.json()
    file_path = (payload.get("result") or {}).get("file_path")
    if not payload.get("ok") or not file_path:
        raise TelegramFileError("Telegram no devolvió una ruta para el archivo")

    # La ruta la construye Telegram, pero se valida igualmente: es entrada
    # externa y se concatena a una URL. Un '..' permitiría salir del prefijo.
    if file_path.startswith("/") or ".." in file_path.split("/"):
        raise TelegramFileError("Telegram devolvió una ruta con un formato inesperado")

    return str(file_path)


async def stream_file(
    client: httpx.AsyncClient,
    token: str,
    file_path: str,
    chunk_size: int,
) -> AsyncIterator[bytes]:
    """Retransmite el contenido del archivo por trozos.

    El generador abre la respuesta remota de forma perezosa: si el consumidor
    corta la conexión, ``httpx`` cierra también la descarga hacia Telegram en
    lugar de seguir bajando un video completo que nadie va a recibir.
    """

    url = f"{TELEGRAM_API_BASE}/file/bot{token}/{file_path}"
    try:
        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise TelegramFileError(
                    f"Telegram respondió con el estado {response.status_code} "
                    "al descargar el archivo"
                )
            async for chunk in response.aiter_bytes(chunk_size):
                yield chunk
    except httpx.HTTPError as exc:
        # El mensaje de httpx contiene la URL, y la URL contiene el token.
        raise TelegramFileError(
            _redact(f"Se interrumpió la descarga desde Telegram: {exc}", token)
        ) from exc


__all__ = [
    "TELEGRAM_API_BASE",
    "TelegramFileError",
    "TelegramFileNotFoundError",
    "resolve_file_path",
    "stream_file",
]
