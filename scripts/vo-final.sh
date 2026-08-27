#!/usr/bin/env bash
# Arma video/public/VO-final.mp3, la locución que usa la composición.
#
# «VO fix.mp3» regrabó la cola porque el VO original pronunciaba «E-C-U» letra
# por letra en lugar de «ECU 911». El corte cae dentro del silencio que precede
# a «¡Listo!» (53,04–53,61 s del original), así que el empalme no se oye: se
# toman 53,30 s del original, 0,30 s de silencio para reponer la pausa, la cola
# nueva y 0,40 s de cola final.
#
# De la cola nueva se descartan los primeros 0,69 s: ahí hay una risa antes de
# «¡Listo!». La palabra empieza en 0,70 s, después de una caída a −56 dB, así
# que el recorte no toca la voz.
set -euo pipefail

cd "$(dirname "$0")/.."
FFMPEG=video/node_modules/@remotion/compositor-linux-x64-gnu/ffmpeg
CORTE=53.30
RISA=0.69

"$FFMPEG" -hide_banner -y \
  -i video/public/VO.mp3 -i "video/public/VO fix.mp3" \
  -filter_complex "\
[0:a]atrim=0:${CORTE},asetpts=N/SR/TB[base];\
anullsrc=r=44100:cl=mono,atrim=0:0.30,asetpts=N/SR/TB[pausa];\
[1:a]atrim=start=${RISA},asetpts=N/SR/TB[cola];\
anullsrc=r=44100:cl=mono,atrim=0:0.40,asetpts=N/SR/TB[final];\
[base][pausa][cola][final]concat=n=4:v=0:a=1[out]" \
  -map "[out]" -c:a libmp3lame -b:a 128k -ar 44100 -ac 1 \
  video/public/VO-final.mp3

echo "video/public/VO-final.mp3 regenerado"
