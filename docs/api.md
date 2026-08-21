# API de reportes — guía de integración

Servicio REST de **solo lectura** que expone los reportes ciudadanos enviados
por el bot de Telegram. Pensado para que SIGTAR los ingiera de forma continua.

- Base: `http://127.0.0.1:8080` (solo accesible desde esta VM)
- Documentación interactiva: `/docs` · Esquema OpenAPI: `/openapi.json`

## Autenticación

Todas las rutas bajo `/v1` exigen la cabecera:

```
Authorization: Bearer <API_KEY>
```

`/healthz` es la única excepción: la usa el healthcheck del contenedor.

Las claves se configuran en `API_KEYS` (separadas por coma). Para rotarlas sin
cortar el servicio: añade la nueva, migra SIGTAR, y luego retira la anterior.

## Sincronización incremental

El endpoint principal recorre los reportes ordenados por `(updated_at, id)`.

```
GET /v1/reports?since=<ISO-8601>&cursor_id=<uuid>&limit=<1..200>
```

| Parámetro | Descripción |
|---|---|
| `since` | Devuelve lo modificado después de este instante. Omítelo en la primera carga. |
| `cursor_id` | Desempata cuando varios reportes comparten `updated_at`. Requiere `since`. |
| `limit` | Reportes por página. Por defecto 50, máximo 200. |

La respuesta trae `items` y `next`:

```json
{
  "items": [ /* ReportOut */ ],
  "next": { "since": "2026-08-06T12:05:00Z", "cursor_id": "9f1c…" }
}
```

**Bucle de ingesta recomendado:**

1. Guarda el último cursor que procesaste con éxito (`since` + `cursor_id`).
2. Pide páginas con ese cursor hasta que `next` sea `null`.
3. Cuando `next` es `null` estás al día: guarda el cursor y vuelve más tarde.

Dos reglas importantes:

- **Ingiere con *upsert* por `id`, no con *insert*.** Un reporte que se
  modifique después de haberlo leído reaparecerá en una página posterior.
- **Persiste el cursor solo cuando la página quedó guardada.** Si SIGTAR se
  cae a mitad, al reiniciar reprocesa desde el último cursor confirmado y no
  pierde nada.

Solo se publican reportes con estado `SUBMITTED`. Los borradores y los
cancelados son estado interno del flujo del bot.

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/v1/reports` | Lista incremental (arriba) |
| GET | `/v1/reports/{id}` | Detalle de un reporte |
| GET | `/v1/media/{media_id}/content` | Bytes de una foto o video |
| GET | `/v1/event-types` | Catálogo para traducir `event_type_code` |
| GET | `/healthz` | Estado del servicio (sin autenticación) |

### Estructura de un reporte

```json
{
  "id": "3f2a…",
  "reporter_id": "8c11…",
  "report_kind": "EVENT",
  "event_type_code": "LLI",
  "event_type_name": "Lluvias intensas",
  "latitude": -0.7436,
  "longitude": -90.3134,
  "location_accuracy": 12.5,
  "description": "Lluvia intensa en la vía a Bellavista.",
  "media": [
    {
      "id": "b4d7…",
      "media_type": "PHOTO",
      "content_url": "/v1/media/b4d7…/content",
      "mime_type": "image/jpeg",
      "original_file_name": null,
      "file_size": 204800,
      "width": 1280,
      "height": 853,
      "duration_seconds": null,
      "caption": "Vía inundada",
      "created_at": "2026-08-06T12:00:00Z"
    }
  ],
  "created_at": "2026-08-06T11:58:00Z",
  "updated_at": "2026-08-06T12:00:00Z",
  "submitted_at": "2026-08-06T12:00:00Z"
}
```

`report_kind` es `EVENT` o `INCIDENT`. En un `INCIDENT`, `event_type_code` es
`null`. Los códigos de evento vigentes son
`TSU`, `ERV`, `LLI`, `INU`, `OLJ`, `SEQ`, `CQM`, `AMA`, `PLG`, `INF`,
`SIS`, `COI`, `DES`, `CAD` y `VDV`.

Consulte `GET /v1/event-types` para traducir cada código sin replicar la tabla.
Devuelve también la `family` oficial del evento, útil para agrupar en un mapa o
en un tablero:

```json
[
  {
    "code": "LLI",
    "name": "Lluvias intensas",
    "family": "Hidrometeorológico",
    "is_active": true
  }
]
```

Las familias son `Oceanográfico`, `Geológico interno`, `Geológico externo`,
`Hidrometeorológico`, `Ambiental`, `Biológico`, `Tecnológico` y
`Fallo estructural`.

**Sobre `reporter_id`:** identifica de forma estable a quien reporta, para
poder correlacionar varios reportes de la misma persona, pero **no** contiene
su nombre, alias ni identificador de Telegram. Si SIGTAR necesitara contactar a
alguien, hay que decidirlo explícitamente y revisarlo con el responsable de
protección de datos.

### Descarga de evidencias

```
GET /v1/media/{media_id}/content
```

Las fotos y videos no están en disco: viven en los servidores de Telegram y
solo se pueden recuperar con el token del bot. La API descarga y retransmite el
contenido, de modo que **el token nunca sale de esta VM**.

Devuelve los bytes con el `Content-Type` real del archivo. La respuesta va en
`chunked`: usa el `file_size` del JSON del reporte si necesitas conocer el
tamaño de antemano. Descarga en *streaming* — un video puede pesar decenas de
megabytes.

| Código | Significado |
|---|---|
| 200 | Contenido del archivo |
| 401 | Falta la clave o no es válida |
| 404 | La evidencia no existe, su reporte no fue enviado, o expiró en Telegram |
| 502 | Telegram no respondió |

Un 502 es transitorio: reintenta con espera exponencial. Un 404 sobre una
evidencia que antes funcionaba significa que Telegram ya no la conserva; si
SIGTAR necesita las evidencias a largo plazo, debe guardarse una copia propia
en el momento de la ingesta.

## Ejemplos

```bash
KEY="tu_clave"
BASE="http://127.0.0.1:8080"

# Primera carga
curl -s -H "Authorization: Bearer $KEY" "$BASE/v1/reports?limit=50" | jq

# Página siguiente
curl -s -H "Authorization: Bearer $KEY" \
  "$BASE/v1/reports?since=2026-08-06T12:05:00%2B00:00&cursor_id=9f1c…" | jq

# Detalle
curl -s -H "Authorization: Bearer $KEY" "$BASE/v1/reports/3f2a…" | jq

# Evidencia
curl -s -H "Authorization: Bearer $KEY" \
  "$BASE/v1/media/b4d7…/content" -o evidencia.jpg

# Salud
curl -s "$BASE/healthz"
```

Nota: el `+` de la zona horaria debe ir codificado como `%2B` en la URL.

## Puesta en marcha

1. **Crear el rol de solo lectura** (una sola vez):

   ```bash
   docker compose exec -T postgres \
     psql -U galapagos -d galapagos_previene \
     -v api_password="'CLAVE_LARGA_Y_ALEATORIA'" < sql/api_readonly.sql
   ```

2. **Configurar el entorno** en `.env`:

   ```bash
   API_DB_PASSWORD=CLAVE_LARGA_Y_ALEATORIA   # la misma del paso 1
   API_KEYS=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
   API_PORT=8080
   ```

3. **Levantar el servicio**:

   ```bash
   docker compose up -d --build api
   docker compose logs -f api
   curl -s http://127.0.0.1:8080/healthz
   ```

El bot sigue funcionando igual; la API es un contenedor aparte y reiniciarla no
interrumpe la recepción de reportes.

## Notas de seguridad

- La API se conecta con el rol `galapagos_api`, que solo tiene `SELECT`. Aunque
  el servicio fuera comprometido, no puede alterar ni borrar reportes.
- El puerto está publicado en `127.0.0.1`, como PostgreSQL. **Si algún día
  SIGTAR se consume desde fuera de esta VM, hay que poner delante un proxy con
  TLS** — no basta con abrir el puerto.
- El contenedor corre como usuario sin privilegios, con el sistema de archivos
  en solo lectura y `no-new-privileges`.
- El `telegram_file_id` no se publica nunca: usarlo requeriría el token del bot.
