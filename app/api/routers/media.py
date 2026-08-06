"""Descarga de evidencias. La API hace de intermediaria ante Telegram."""

from __future__ import annotations

import logging
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.api.deps import PoolDep, SettingsDep
from app.api.telegram_files import (
    TelegramFileError,
    TelegramFileNotFoundError,
    resolve_file_path,
    stream_file,
)
from app.models import MediaType
from app.repositories.exports import get_submitted_media


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/media", tags=["evidencias"])

# Si Telegram no informó el MIME se declara un tipo genérico. Nunca se deduce
# del nombre del archivo: ese dato lo controla quien envía el reporte.
FALLBACK_MIME = {
    MediaType.PHOTO: "image/jpeg",
    MediaType.VIDEO: "video/mp4",
}


def _content_disposition(file_name: str | None) -> str:
    """Construye la cabecera sin permitir inyección de cabeceras.

    ``original_file_name`` viene del dispositivo de quien reporta y puede
    contener comillas o saltos de línea. Se envía siempre codificado en la
    forma ``filename*`` de RFC 5987, que admite UTF-8 y escapa los caracteres
    problemáticos.
    """

    safe_name = quote(file_name or "evidencia", safe="")
    return f"attachment; filename*=UTF-8''{safe_name}"


@router.get(
    "/{media_id}/content",
    summary="Descarga los bytes de una foto o video",
    responses={
        200: {"content": {"application/octet-stream": {}}},
        404: {"description": "La evidencia no existe o su reporte no fue enviado"},
        502: {"description": "Telegram no pudo entregar el archivo"},
    },
)
async def download_media(
    media_id: UUID,
    request: Request,
    pool: PoolDep,
    settings: SettingsDep,
) -> StreamingResponse:
    """Retransmite el archivo desde Telegram sin guardarlo en disco.

    El ``telegram_file_id`` no se publica en ningún momento: usarlo requiere el
    token del bot, que se queda en este proceso.
    """

    media = await get_submitted_media(pool, media_id)
    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe una evidencia con ese identificador",
        )

    token = settings.telegram_bot_token
    client = request.app.state.http_client

    try:
        file_path = await resolve_file_path(client, token, media.telegram_file_id)
    except TelegramFileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La evidencia ya no está disponible en Telegram",
        ) from exc
    except TelegramFileError as exc:
        logger.warning("Fallo al resolver la evidencia %s: %s", media_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo obtener el archivo desde Telegram",
        ) from exc

    media_type = media.mime_type or FALLBACK_MIME[media.media_type]
    headers = {
        "Content-Disposition": _content_disposition(media.original_file_name),
        # El contenido nunca cambia para un id dado: se puede cachear mucho
        # tiempo, pero en privado porque la respuesta va autenticada.
        "Cache-Control": "private, max-age=86400",
    }
    # No se declara Content-Length a partir de `file_size`: ese valor lo
    # informó Telegram al recibir el mensaje y no tiene por qué coincidir con
    # los bytes que devuelve ahora la descarga. Un valor mayor deja al cliente
    # esperando y uno menor trunca el archivo. La respuesta va en `chunked`, y
    # el tamaño esperado ya viaja en el JSON del reporte.

    return StreamingResponse(
        stream_file(client, token, file_path, settings.media_chunk_size),
        media_type=media_type,
        headers=headers,
    )
