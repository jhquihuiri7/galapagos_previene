# Prompt para el equipo/agente de SIGTAR

Copia el bloque siguiente tal cual. Antes de enviarlo, reemplaza los dos
marcadores del principio:

- `<STACK>` — la tecnología en la que se implementa la ingesta (Django, Laravel,
  Node/Express, .NET…). Si no lo indicas, el resultado será pseudocódigo.
- `<API_KEY>` — **no la pegues en el prompt.** Deja el marcador y entrega la
  clave por un canal aparte, para que quede en una variable de entorno y no en
  el historial de un chat ni en el repositorio.

---

```text
Necesito integrar en SIGTAR (<STACK>) la ingesta de reportes ciudadanos
provenientes del sistema "Galápagos Previene". Los reportes llegan por un bot
de Telegram y se exponen mediante una API REST de solo lectura que corre en
esta misma VM.

## Conexión

- Base URL: http://127.0.0.1:8080
- Autenticación: cabecera `Authorization: Bearer <API_KEY>` en TODAS las rutas
  bajo /v1. La clave debe leerse de una variable de entorno; no la escribas en
  el código ni la subas al repositorio.
- Documentación interactiva: /docs — Esquema OpenAPI: /openapi.json
  (puedes descargar el OpenAPI para generar el cliente en lugar de escribirlo
  a mano; si lo haces, verifica igualmente las reglas de sincronización de
  abajo, que el esquema no expresa por sí solo).

## Endpoints

| Método | Ruta                          | Uso                                    |
|--------|-------------------------------|----------------------------------------|
| GET    | /v1/reports                   | Lista incremental (endpoint principal) |
| GET    | /v1/reports/{id}              | Detalle de un reporte                  |
| GET    | /v1/media/{media_id}/content  | Bytes de una foto o video              |
| GET    | /v1/event-types               | Catálogo de tipos de evento            |
| GET    | /healthz                      | Estado del servicio (sin autenticación)|

## Estructura de un reporte

{
  "id": "3f2a…",                       // UUID, clave primaria de la ingesta
  "reporter_id": "8c11…",              // UUID estable de quien reporta
  "report_kind": "EVENT",              // "EVENT" o "INCIDENT"
  "event_type_code": "RAIN",           // "RAIN" | "TSUNAMI" | "FIRE" | null
  "event_type_name": "Lluvia",
  "latitude": -0.7436,
  "longitude": -90.3134,
  "location_accuracy": 12.5,           // metros; puede ser null
  "description": "Lluvia intensa en la vía a Bellavista.",
  "media": [
    {
      "id": "b4d7…",
      "media_type": "PHOTO",           // "PHOTO" o "VIDEO"
      "content_url": "/v1/media/b4d7…/content",
      "mime_type": "image/jpeg",
      "original_file_name": null,
      "file_size": 204800,             // bytes, informativo
      "width": 1280, "height": 853,
      "duration_seconds": null,        // solo en video
      "caption": "Vía inundada",
      "created_at": "2026-08-06T12:00:00Z"
    }
  ],
  "created_at":   "2026-08-06T11:58:00Z",
  "updated_at":   "2026-08-06T12:00:00Z",
  "submitted_at": "2026-08-06T12:00:00Z"
}

Notas del contrato:
- En un reporte de tipo INCIDENT, `event_type_code` y `event_type_name` son
  null. En un EVENT siempre vienen informados.
- `latitude`/`longitude` pueden ser null en teoría, pero la API solo publica
  reportes enviados, que siempre tienen ubicación. Trátalos como opcionales de
  todos modos.
- `reporter_id` identifica a la persona de forma estable para poder agrupar sus
  reportes, pero NO contiene nombre, alias ni identificador de Telegram. Si
  SIGTAR necesitara contactar a quien reporta, hay que solicitarlo: es una
  decisión de protección de datos, no un campo que falte por error.
- Todas las marcas de tiempo son ISO-8601 con zona horaria (UTC).

## Sincronización incremental (lo más importante)

GET /v1/reports?since=<ISO-8601>&cursor_id=<uuid>&limit=<1..200>

- `since`: devuelve lo modificado después de ese instante. Omítelo en la carga
  inicial.
- `cursor_id`: desempata cuando varios reportes comparten el mismo
  `updated_at`. Requiere `since` (enviarlo solo devuelve HTTP 400).
- `limit`: por defecto 50, máximo 200.

Respuesta:

{ "items": [ /* reportes */ ],
  "next": { "since": "2026-08-06T12:05:00Z", "cursor_id": "9f1c…" } }

Implementa este bucle:

1. Recupera el último cursor guardado (`since` + `cursor_id`); en la primera
   ejecución no hay ninguno y se llama sin parámetros.
2. Pide una página, procesa y persiste sus `items`.
3. Solo DESPUÉS de guardar la página correctamente, persiste el `next` como
   nuevo cursor.
4. Repite mientras `next` no sea null.
5. Cuando `next` es null estás al día: termina y vuelve a ejecutar más tarde
   con el cursor guardado (un job cada 1–5 minutos es razonable).

Tres reglas que debes respetar, porque el sistema depende de ellas:

- INGIERE CON UPSERT POR `id`, NUNCA CON INSERT. Un reporte que se modifique
  después de haberlo leído reaparecerá en una página posterior. Un INSERT
  simple provocará errores de clave duplicada.
- PERSISTE EL CURSOR SOLO CUANDO LA PÁGINA YA QUEDÓ GUARDADA. Si SIGTAR se cae
  a mitad de la ingesta, al reiniciar debe reprocesar desde el último cursor
  confirmado. Reprocesar es inofensivo (el upsert lo absorbe); saltarse una
  página pierde reportes de forma permanente.
- GUARDA EL CURSOR EN ALMACENAMIENTO PERSISTENTE (tabla o similar), no en
  memoria: debe sobrevivir a un reinicio del servicio.

Solo se publican reportes en estado enviado. Los borradores y los cancelados
son estado interno del bot y nunca aparecen.

## Descarga de evidencias

GET /v1/media/{media_id}/content  (con la misma cabecera Authorization)

Devuelve los bytes con su `Content-Type` real. La respuesta va en `chunked`, no
trae `Content-Length`: usa el `file_size` del JSON si necesitas el tamaño por
adelantado, y DESCARGA EN STREAMING — un video puede pesar decenas de MB y no
debe cargarse entero en memoria.

Las fotos y videos NO están en disco del lado emisor: viven en los servidores
de Telegram y la API actúa de intermediaria. Consecuencia práctica: si SIGTAR
necesita conservar las evidencias a largo plazo, debe descargar y guardar su
propia copia en el momento de la ingesta. Un archivo que hoy responde 200
puede responder 404 más adelante si Telegram deja de conservarlo.

`original_file_name` proviene del dispositivo de quien reporta: es dato no
confiable. No lo uses para construir rutas en disco ni para deducir el tipo de
contenido; apóyate en `mime_type` y `media_type`, y genera tú el nombre del
archivo (por ejemplo, a partir del `id` de la evidencia).

## Manejo de errores

| Código | Significado                            | Qué hacer                        |
|--------|----------------------------------------|----------------------------------|
| 200    | Correcto                               | —                                |
| 400    | Parámetros inválidos (p. ej. `cursor_id` sin `since`) | Corregir la petición; no reintentar |
| 401    | Falta la clave o no es válida          | No reintentar; revisar config    |
| 404    | No existe, o la evidencia expiró en Telegram | No reintentar; registrar   |
| 422    | Parámetro fuera de rango (p. ej. limit>200) | Corregir; no reintentar     |
| 502    | Telegram no respondió                  | Transitorio: reintentar con espera exponencial |
| 503    | La API no alcanza su base de datos     | Transitorio: reintentar          |

Un 502 o 503 a mitad de la ingesta NO debe avanzar el cursor: aborta la
ejecución y deja que el siguiente ciclo retome desde donde quedó.

## Entregable que espero

1. Un cliente HTTP para esta API, con la clave leída de variable de entorno,
   timeouts explícitos y reintentos con espera exponencial solo para 502/503.
2. El modelo/tabla de destino en SIGTAR más la tabla que guarda el cursor.
3. El job de sincronización con el bucle descrito, idempotente y seguro ante
   reinicios.
4. La descarga en streaming de las evidencias asociadas a cada reporte.
5. Logs que permitan auditar cada ciclo: cuántos reportes se ingirieron, cuál
   es el cursor actual y qué errores hubo. Nunca registres la API key.
6. Pruebas del bucle de sincronización que cubran al menos: página única,
   varias páginas, reingesta de un reporte ya visto (upsert), y caída a mitad
   de la ingesta sin avance del cursor.

Empieza proponiéndome el diseño del modelo de datos y del job antes de escribir
el código completo.
```
