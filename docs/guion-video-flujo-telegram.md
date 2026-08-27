# Guion del video · Flujo del bot en Telegram

Composición `FlujoTelegram` — 1080×1920, **60 fps**, 3849 frames = **64,15 s**.
Intro de 342 frames (0:00–0:05,7) + chat de 3507 frames (0:05,7–1:04,1).

Las animaciones se escribieron contando frames a 30 fps; `src/telegram/timing.ts`
las traduce a la tasa real con `f()`, así que subir los fps no mueve nada. Los
frames de esta tabla son los de 60 fps.

La locución manda. El audio es `video/public/VO-final.mp3` (64,10 s), el montaje
de `VO.mp3` con la cola regrabada de `VO fix.mp3`, sin la risa que esta traía
antes de «¡Listo!»; lo arma `scripts/vo-final.sh`. Los tiempos de abajo se midieron sobre ese montaje; cada evento de `video/src/telegram/script.ts` se
declara con el segundo absoluto en que debe verse, así que la tabla y el código
se leen en paralelo. Si se cambia el audio hay que rehacer las dos cosas.

## Voiceover (lo que dice el audio actual)

| # | Entra | Sale | Locución |
|---|---|---|---|
| 1 | 0:00,0 | 0:01,3 | Galápagos Previene. |
| 2 | 0:02,0 | 0:05,5 | Avisa lo que está pasando en las islas en menos de un minuto. |
| 3 | 0:06,1 | 0:09,1 | Abre el bot en Telegram y escribe «iniciar». |
| 4 | 0:09,7 | 0:14,7 | El bot te saluda y te pregunta qué quieres reportar: un evento o un incidente. |
| 5 | 0:15,2 | 0:16,5 | Presiona «Evento». |
| 6 | 0:16,8 | 0:21,8 | Aparecen los diez eventos adversos del catálogo oficial, desde tsunami hasta vendaval. |
| 7 | 0:22,4 | 0:26,0 | Presiona el que corresponde. Aquí, incendio forestal. |
| 8 | 0:26,8 | 0:29,8 | El bot confirma el evento y te pide fotos o videos. |
| 9 | 0:30,4 | 0:33,9 | Selecciónalos todos y mándalos juntos en un solo mensaje. |
| 10 | 0:34,5 | 0:37,6 | La carga es única. Después ya no se agregan archivos. |
| 11 | 0:38,4 | 0:41,0 | El bot te confirma cuántos archivos recibió. |
| 12 | 0:41,4 | 0:44,0 | Luego presiona el botón para compartir tu ubicación. |
| 13 | 0:44,7 | 0:49,6 | Con la ubicación registrada solo falta un paso: contar brevemente qué ocurrió. |
| 14 | 0:50,2 | 0:53,0 | Escribes la descripción y el reporte se envía. |
| 15 | 0:53,6 | 0:56,3 | Listo. Tu reporte ya está en la sala de monitoreo. |
| 16 | 0:56,6 | 1:00,3 | En caso de emergencia, llama al ECU 911. |
| 17 | 1:00,8 | 1:03,5 | Y escribe «nuevo» cuando quieras reportar algo más. |

### Diferencias con el guion previo

Los bloques 15 a 17 vienen de `VO fix.mp3`, que corrige la pronunciación de
«ECU 911»; de ese archivo se descartan los primeros 0,69 s, donde hay una risa
antes de «¡Listo!». El resto del audio sigue sin coincidir del todo con lo que estaba
escrito; queda pendiente de decidir y el video está montado sobre lo que se
oye:

- Bloque 2 dice «avisa lo que está pasando en las islas», no «reporta lo que
  está sucediendo en Galápagos». Para cambiarlo hay que regrabar.
- Bloques 5 y 7 pronuncian «preciona» y el 12, «presione», en lugar de
  «presiona».
- La locución partió varias frases largas en dos, así que hay 17 bloques donde
  el guion escrito tenía 11.

## Marcas de la animación

| Frame | Tiempo | Qué pasa en pantalla |
|---|---|---|
| 0 | 0:00,0 | Intro: el bot recién abierto, con el botón INICIAR |
| 298 | 0:05,0 | Se pulsa INICIAR |
| 342 | 0:05,7 | Entra el chat |
| 366 | 0:06,1 | Se abre el menú de comandos de Telegram |
| 522 | 0:08,7 | Se cierra el menú de comandos |
| 534 | 0:08,9 | El usuario envía `/iniciar` |
| 582 | 0:09,7 | Bienvenida con los botones Evento / Incidente |
| 972 | 0:16,2 | Se presiona «Evento» |
| 1014 | 0:16,9 | El bot edita su mensaje: los diez eventos adversos |
| 1518 | 0:25,3 | Se presiona «Incendio forestal» |
| 1614 | 0:26,9 | El bot confirma el evento y pide fotos y videos |
| 1824 | 0:30,4 | Se abre la hoja de adjuntos: cámara y galería |
| 2304 | 0:38,4 | Se envía el álbum de 3 fotos |
| 2382 | 0:39,7 | «Recibí 3 archivo(s)» y el bot pide la ubicación |
| 2386 | 0:39,8 | Aparece el teclado «Compartir mi ubicación» |
| 2658 | 0:44,3 | El usuario comparte su ubicación |
| 2694 | 0:44,9 | El bot pide la descripción |
| 3030 | 0:50,5 | El usuario escribe la descripción |
| 3168 | 0:52,8 | El bot confirma el envío del reporte |
| 3849 | 1:04,1 | Fin |

El álbum entra siempre 8 s después de abrir la hoja de adjuntos: es lo que
tarda la animación interna hasta pulsar Enviar (`SEND` en `AttachSheet.tsx`).
Si se mueve uno, se mueve el otro.

## Render

```
cd video
npx remotion render FlujoTelegram out/flujo-telegram-4k60.mp4 \
  --scale=2 --crf=10 --image-format=png
```

`--scale=2` lleva los 1080×1920 de la composición a 2160×3840 sin tocar el
layout, que está en píxeles. `--crf=10` es H.264 casi sin pérdida y
`--image-format=png` evita el JPEG intermedio. Sin banderas, el mismo comando
entrega 1080×1920 y pesa una décima parte.

## Captions (rótulos en pantalla)

Textos cortos, una línea, en la franja inferior. Todavía no están
implementados en Remotion: esta tabla es la especificación.

| # | Entra | Sale | Caption |
|---|---|---|---|
| 1 | 0:06,1 | 0:09,5 | Paso 1 · Escribe /iniciar |
| 2 | 0:09,7 | 0:14,7 | Paso 2 · Elige: evento o incidente |
| 3 | 0:16,9 | 0:22,0 | Paso 3 · Elige el tipo de evento |
| 4 | 0:26,9 | 0:37,7 | Paso 4 · Envía fotos y videos en una sola carga |
| 5 | 0:39,8 | 0:44,1 | Paso 5 · Comparte tu ubicación |
| 6 | 0:44,9 | 0:49,6 | Paso 6 · Cuenta qué ocurrió |
| 7 | 0:53,6 | 1:00,3 | Reporte enviado · Emergencias: ECU 911 |
