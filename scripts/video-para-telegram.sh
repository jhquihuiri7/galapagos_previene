#!/usr/bin/env bash
# Produce video/out/flujo-telegram-1080p60.mp4, el render que envía /tutorial.
#
# El máster 4K de Remotion (2160×3840 a 60 fps) sale en H.264 High nivel 5.2 y
# el reproductor integrado de Telegram no lo decodifica: entrega el archivo pero
# propone abrirlo con una aplicación externa, así que el tutorial no se ve. El
# techo seguro es el nivel 4.2, que cubre 1080p a 60 fps en cualquier teléfono.
#
# No se reutiliza el render de 1080p de Remotion porque va a 1.17 Mbps y 30 fps.
# Bajar desde el máster con lanczos y CRF 20 conserva la nitidez del texto de la
# interfaz, que es casi todo lo que muestra el video, y mantiene los 60 fps.
# El resultado ronda los 9,5 MB: si hiciera falta más nitidez, bajar CRF a 18
# cabe de sobra en el límite de 50 MB.
#
# `in_range=full:out_range=limited` corrige la otra rareza del máster: Remotion
# escribe yuvj420p (rango completo) y los reproductores que asumen rango
# limitado muestran los negros aplastados.
set -euo pipefail

cd "$(dirname "$0")/.."
FFMPEG=video/node_modules/@remotion/compositor-linux-x64-gnu/ffmpeg
MASTER=video/out/flujo-telegram-4k60.mp4
SALIDA=video/out/flujo-telegram-1080p60.mp4

"$FFMPEG" -hide_banner -y \
  -i "$MASTER" \
  -vf "scale=1080:1920:flags=lanczos:in_range=full:out_range=limited,format=yuv420p" \
  -c:v libx264 -profile:v high -level:v 4.2 -preset slow -crf 20 \
  -maxrate 6M -bufsize 12M -g 120 \
  -c:a aac -b:a 128k -ar 48000 -ac 2 \
  -movflags +faststart \
  "$SALIDA"

# `+faststart` deja el átomo moov al inicio: la reproducción arranca sin
# descargar el archivo completo.
video/node_modules/@remotion/compositor-linux-x64-gnu/ffprobe -v error \
  -select_streams v:0 \
  -show_entries stream=width,height,profile,level,avg_frame_rate,pix_fmt \
  -of default=noprint_wrappers=1 "$SALIDA"
