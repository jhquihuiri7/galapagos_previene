# Guion del video · Flujo del bot en Telegram

Composición `FlujoTelegram` — 1080×1920, 30 fps, 1692 frames = **56,4 s**.
Estructura: intro de 100 frames (0:00–0:03,3) + chat de 1592 frames (0:03,3–0:56,4).

Los tiempos salen del guion real de animación en `video/src/telegram/script.ts`.
Si cambian las pausas (`at(...)`) hay que recalcular esta tabla.

## Marcas de la animación

| Frame | Tiempo | Qué pasa en pantalla |
|---|---|---|
| 0 | 0:00,0 | Intro (logo y título) |
| 120 | 0:04,0 | Se abre el menú de comandos de Telegram |
| 190 | 0:06,3 | Se cierra el menú de comandos |
| 196 | 0:06,5 | El usuario envía `/iniciar` |
| 276 | 0:09,2 | Mensaje de bienvenida con los botones Evento / Incidente |
| 386 | 0:12,9 | Se presiona «Evento» |
| 428 | 0:14,3 | El bot edita su mensaje: los diez eventos adversos |
| 638 | 0:21,3 | Se presiona «Incendio forestal» |
| 678 | 0:22,6 | El bot pide fotos y videos |
| 758 | 0:25,3 | Se abre la galería del teléfono |
| 998 | 0:33,3 | Se envía el álbum de 3 fotos |
| 1073 | 0:35,8 | El bot confirma «Recibí 3 archivo(s)» y pide ubicación |
| 1075 | 0:35,8 | Aparece el teclado «Compartir mi ubicación» |
| 1205 | 0:40,2 | El usuario comparte su ubicación |
| 1257 | 0:41,9 | El bot pide la descripción |
| 1392 | 0:46,4 | El usuario escribe la descripción |
| 1452 | 0:48,4 | El bot confirma el envío del reporte |
| 1692 | 0:56,4 | Fin |

## Voiceover

Ritmo objetivo: ~2,5 palabras por segundo. Cada bloque entra al inicio de su
tiempo y termina antes del siguiente; los redondeos dejan aire deliberado.

| # | Entra | Sale | Locución |
|---|---|---|---|
| 1 | 0:00,0 | 0:03,3 | Galápagos Previene: reporta lo que está sucediendo en Galápagos en menos de un minuto. |
| 2 | 0:03,5 | 0:06,5 | Abre el bot en Telegram y escribe «iniciar». |
| 3 | 0:07,0 | 0:12,8 | El bot te saluda y te pregunta qué quieres reportar: un evento o un incidente. Presiona «Evento». |
| 4 | 0:13,5 | 0:21,2 | Aparecen los diez eventos adversos del catálogo oficial, desde tsunami hasta vendaval. Presiona el que corresponde; aquí, incendio forestal. |
| 5 | 0:21,5 | 0:25,2 | El bot confirma el evento y te pide fotos o videos. |
| 6 | 0:25,5 | 0:33,2 | Selecciónalos todos y mándalos juntos en un solo mensaje: la carga es única, después ya no se agregan archivos. |
| 7 | 0:33,5 | 0:35,7 | El bot te confirma cuántos archivos recibió. |
| 8 | 0:36,0 | 0:40,1 | Luego presiona el botón para compartir tu ubicación. |
| 9 | 0:40,5 | 0:46,3 | Con la ubicación registrada solo falta un paso: contar brevemente qué ocurrió. |
| 10 | 0:46,5 | 0:48,3 | Escribes la descripción y el reporte se envía. |
| 11 | 0:48,6 | 0:56,4 | Listo. Tu reporte ya está en la sala de monitoreo. En caso de emergencia, llama al ECU 911. Y escribe «nuevo» cuando quieras reportar algo más. |

## Captions (rótulos en pantalla)

Textos cortos, una línea, en la franja inferior. Sustituyen a los rótulos de
paso que antes se superponían al chat.

| # | Entra | Sale | Caption |
|---|---|---|---|
| 1 | 0:06,5 | 0:09,0 | Paso 1 · Escribe /iniciar |
| 2 | 0:09,2 | 0:12,8 | Paso 2 · Elige: evento o incidente |
| 3 | 0:14,3 | 0:21,2 | Paso 3 · Elige el tipo de evento |
| 4 | 0:22,6 | 0:33,2 | Paso 4 · Envía fotos y videos en una sola carga |
| 5 | 0:35,8 | 0:40,1 | Paso 5 · Comparte tu ubicación |
| 6 | 0:41,9 | 0:46,3 | Paso 6 · Cuenta qué ocurrió |
| 7 | 0:48,4 | 0:54,0 | Reporte enviado · Emergencias: ECU 911 |
