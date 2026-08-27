#!/usr/bin/env python3
"""Sube el video del tutorial una vez y muestra su ``file_id`` de Telegram.

En producción el MP4 no está disponible: ``video/out/`` no se versiona ni entra
en la imagen de Docker. La solución es subirlo una sola vez desde esta máquina y
guardar el identificador que devuelve Telegram en ``TUTORIAL_VIDEO_FILE_ID``; a
partir de ahí el bot reenvía el mismo archivo sin transferir bytes.

Uso:
    python3 scripts/tutorial-file-id.py [chat_id] [ruta_del_video]

Sin ``chat_id`` se consulta el último mensaje recibido por el bot, así que basta
con escribirle algo antes de ejecutar el script. Eso requiere que el bot esté
detenido: Telegram no entrega ``getUpdates`` a dos clientes a la vez.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError
from telegram.request import HTTPXRequest

RAIZ = Path(__file__).resolve().parent.parent
VIDEO_PREDETERMINADO = RAIZ / "video" / "out" / "flujo-telegram-1080p60.mp4"

# La subida puede tardar varios minutos en una conexión lenta.
TIMEOUT = 600.0

# Límite de la API de bots para subir un archivo con multipart/form-data.
LIMITE_SUBIDA_MB = 50


async def ultimo_chat(bot: Bot) -> int:
    """Devuelve el chat del último mensaje pendiente en la cola de Telegram."""

    updates = await bot.get_updates(limit=100, timeout=0)
    for update in reversed(updates):
        mensaje = update.effective_message
        if mensaje is not None:
            return mensaje.chat_id
    raise SystemExit(
        "No hay mensajes recientes. Escríbele algo al bot y vuelve a ejecutar "
        "el script, o pasa el chat_id como primer argumento."
    )


async def principal(chat_id: int | None, video: Path) -> None:
    """Envía el video al chat indicado e imprime la línea lista para el .env."""

    load_dotenv(dotenv_path=RAIZ / ".env", override=False)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN en el entorno o en .env.")

    if not video.is_file():
        raise SystemExit(f"No existe el video {video}. Renderízalo primero.")
    peso_mb = video.stat().st_size / 1_000_000
    if peso_mb > LIMITE_SUBIDA_MB:
        raise SystemExit(
            f"{video.name} pesa {peso_mb:.1f} MB y la API de bots admite hasta "
            f"{LIMITE_SUBIDA_MB} MB. Usa el render de compatibilidad en "
            "video/out/flujo-telegram-1080p60.mp4."
        )

    peticion = HTTPXRequest(read_timeout=TIMEOUT, write_timeout=TIMEOUT)
    async with Bot(token, request=peticion) as bot:
        destino = chat_id if chat_id is not None else await ultimo_chat(bot)
        print(f"Subiendo {video.name} ({peso_mb:.1f} MB) al chat {destino}…")
        try:
            mensaje = await bot.send_video(
                chat_id=destino,
                video=video,
                caption="Prueba de subida del tutorial.",
                supports_streaming=True,
                read_timeout=TIMEOUT,
                write_timeout=TIMEOUT,
            )
        except TelegramError as exc:
            raise SystemExit(f"Telegram rechazó la subida: {exc}") from exc

    if mensaje.video is None:
        raise SystemExit(
            "Telegram no lo guardó como video. Revisa que sea un MP4 H.264."
        )
    print("\nAgrega esta línea al .env del servidor:\n")
    print(f"TUTORIAL_VIDEO_FILE_ID={mensaje.video.file_id}")


if __name__ == "__main__":
    argumentos = sys.argv[1:]
    chat = None
    if argumentos:
        try:
            chat = int(argumentos[0])
        except ValueError as exc:
            raise SystemExit(f"chat_id debe ser numérico: {argumentos[0]}") from exc
    ruta = Path(argumentos[1]).expanduser() if len(argumentos) > 1 else VIDEO_PREDETERMINADO
    asyncio.run(principal(chat, ruta))
