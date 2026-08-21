# Flujo de mensajes de Telegram — Galápagos Previene

## 1. Resumen del recorrido

```mermaid
flowchart TD
    START["/start, /iniciar o /nuevo"] --> OLD{"¿Existe un borrador activo?"}
    OLD -->|Sí| CANCEL_OLD["Avisar que fue cancelado"]
    OLD -->|No| KIND
    CANCEL_OLD --> KIND["Elegir Evento o Incidente"]

    KIND -->|🌋 Evento| EVENT_TYPE["Elegir Lluvia, Tsunami o Incendio"]
    KIND -->|⚠️ Incidente| MEDIA["Enviar evidencias"]
    EVENT_TYPE --> MEDIA

    MEDIA -->|Foto, video o documento compatible| MEDIA_OK["Confirmar archivo y mostrar contador"]
    MEDIA_OK --> MEDIA
    MEDIA -->|Finalizar sin archivos| MEDIA_EMPTY["Alerta: se necesita al menos uno"]
    MEDIA_EMPTY --> MEDIA
    MEDIA -->|✅ Finalizar fotos y videos| LOCATION["Compartir ubicación"]

    LOCATION -->|Ubicación válida| DESCRIPTION["Escribir descripción de 10+ caracteres"]
    LOCATION -->|Contenido o ubicación inválida| LOCATION
    DESCRIPTION -->|Descripción corta o no textual| DESCRIPTION
    DESCRIPTION -->|Texto válido| SUBMITTED["Confirmación de envío y aviso del 911"]

    START -.->|/cancelar durante el flujo| CANCELLED["Cancelar el reporte"]
    START -.->|/ayuda en cualquier momento| HELP["Mostrar ayuda sin cambiar el estado"]
```

El reporte se considera enviado únicamente después de recibir una descripción
válida. Antes de eso permanece como borrador (`DRAFT`) en PostgreSQL.

## 3. Flujo principal, mensaje por mensaje

### Paso 1 — Iniciar o reiniciar

**Acción del usuario**

Envía `/start`, `/iniciar` o `/nuevo`.

Si ya tenía un borrador activo, primero recibe un mensaje independiente:

> El borrador anterior fue cancelado.

Ese mensaje también ordena ocultar cualquier teclado de respuesta anterior.
Después, tanto para un usuario nuevo como para uno que reinició, el bot envía:

> 🌿 ¡Hola! Bienvenido a Galápagos Previene.
>
> Aquí puedes avisarnos de algo que esté pasando en las islas.
>
> ¿Qué quieres reportar?

**Botones inline, en una misma fila**

- `🌋 Evento`
- `⚠️ Incidente`

**Estado de conversación:** `CHOOSE_KIND`.

### Paso 2A — Ruta Evento

**Acción del usuario**

Pulsa `🌋 Evento`.

El bot crea el borrador y edita el mensaje de selección para mostrar:

> ¿Qué tipo de evento quieres reportar?

**Botones inline, uno por fila**

- `🌧️ Lluvia`
- `🌊 Tsunami`
- `🔥 Incendio`

**Estado de conversación:** `CHOOSE_EVENT_TYPE`.

Cuando el usuario elige cualquiera de los tres tipos, el bot guarda la
selección y vuelve a editar ese mensaje:

> Evento: `{Lluvia | Tsunami | Incendio}` ✓
>
> 📸 Ahora envíame fotos o videos de lo que está pasando.
>
> Puedes enviar varios.

Inmediatamente envía un segundo mensaje:

> Cuando termines, pulsa el botón de abajo.

**Botón inline**

- `✅ Finalizar fotos y videos`

**Siguiente estado:** `WAITING_MEDIA`.

### Paso 2B — Ruta Incidente

**Acción del usuario**

Pulsa `⚠️ Incidente`.

No se solicita un subtipo. El bot crea el borrador y edita el mensaje de
selección para mostrar:

> Incidente ✓
>
> 📸 Ahora envíame fotos o videos de lo que está pasando.
>
> Puedes enviar varios.

Después envía un segundo mensaje:

> Cuando termines, pulsa el botón de abajo.

**Botón inline**

- `✅ Finalizar fotos y videos`

**Siguiente estado:** `WAITING_MEDIA`.

### Paso 3 — Registrar fotos y videos

El usuario puede enviar repetidamente:

- una foto nativa de Telegram;
- un video nativo de Telegram;
- una imagen enviada como documento, si su MIME comienza con `image/`;
- un video enviado como documento, si su MIME comienza con `video/`;
- un álbum, que Telegram entrega al bot como varios mensajes individuales.

El pie de foto, si existe, se almacena como metadato. No se descarga el archivo:
se conservan sus identificadores de Telegram.

Por cada archivo nuevo aceptado, el bot responde:

> ✅ Archivo recibido (`{cantidad}` de `{límite}`).
>
> Puedes enviar más o pulsar el botón para continuar.

El mensaje conserva el botón:

- `✅ Finalizar fotos y videos`

`{límite}` corresponde a `MAX_MEDIA_FILES`; el valor predeterminado es **10**.

Si Telegram vuelve a entregar el mismo mensaje y el archivo ya había sido
registrado, el bot responde:

> ℹ️ Ese archivo ya lo tenía (`{cantidad}` de `{límite}`).
>
> Puedes enviar más o pulsar el botón para continuar.

Si ya se alcanzó el máximo configurado:

> Máximo `{límite}` archivos. Pulsa el botón para continuar.

Si se envía texto, audio, un documento con MIME no admitido u otro contenido
en este paso:

> 📸 Necesito una foto o video. Si ya terminaste, pulsa el botón.

La implementación también contiene este mensaje defensivo para un archivo que
llegue al extractor pero no pueda clasificarse como imagen o video:

> Formato no válido. Envía una foto o video.

Todos estos casos mantienen el estado `WAITING_MEDIA` y vuelven a mostrar el
botón de finalización.

### Paso 4 — Finalizar evidencias

**Acción del usuario**

Pulsa `✅ Finalizar fotos y videos`.

Si todavía no registró ninguna evidencia, Telegram muestra una alerta:

> Envíame al menos una foto o video antes de continuar.

El usuario permanece en `WAITING_MEDIA`.

Si existe al menos una evidencia, el bot edita el mensaje que contenía el
botón:

> ✅ Listo, recibí `{cantidad}` archivo(s).

Después envía un nuevo mensaje:

> 📍 Compárteme tu ubicación.

**Botón de teclado de respuesta**

- `📍 Compartir mi ubicación`

Telegram solicita el consentimiento del usuario antes de compartir la
ubicación. También es válida una ubicación elegida manualmente desde el mapa.

**Siguiente estado:** `WAITING_LOCATION`.

### Paso 5 — Compartir la ubicación

Al recibir una ubicación válida, el bot guarda latitud, longitud y precisión,
oculta el teclado de ubicación y responde:

> ✅ Listo.
>
> ✍️ Último paso: cuéntame brevemente qué ocurrió.

**Siguiente estado:** `WAITING_DESCRIPTION`.

Las coordenadas deben ser numéricas y finitas, con latitud entre `-90` y `90`
y longitud entre `-180` y `180`.

Si Telegram entrega un objeto de ubicación con coordenadas inválidas:

> Esa ubicación no es válida. Compártela otra vez.

Si la ubicación es válida pero ya no puede guardarse en el paso actual:

> No pudimos guardar la ubicación. Compártela otra vez o usa /iniciar.

Si el usuario envía texto, archivos u otro contenido en lugar de una ubicación:

> 📍 Usa el botón para compartir tu ubicación.

En los tres casos se mantiene `WAITING_LOCATION` y se vuelve a mostrar el botón
`📍 Compartir mi ubicación`.

### Paso 6 — Escribir la descripción

El usuario debe enviar un mensaje de texto con al menos 10 caracteres después
de quitar los espacios del principio y del final. Los espacios internos se
conservan.

Si el texto tiene menos de 10 caracteres:

> La descripción debe tener al menos 10 caracteres.

Si envía una foto, video, ubicación u otro contenido no textual:

> ✍️ Escríbeme la descripción como mensaje de texto.

Ambas respuestas mantienen el estado `WAITING_DESCRIPTION`.

### Paso 7 — Confirmación final

Con una descripción válida, el bot vuelve a comprobar la integridad del
reporte, lo marca como enviado (`SUBMITTED`), limpia la sesión temporal y
responde:

> ✅ ¡Listo! Tu reporte fue enviado.
>
> Gracias por ayudar a cuidar Galápagos 🌿
>
> 🚨 Si es una emergencia, llama al 911.
>
> Escribe /nuevo para reportar algo más.

Por decisión de producto la confirmación no muestra el identificador interno
del reporte ni el conteo de archivos: no son datos útiles para el usuario en ese
momento. El aviso del 911 recuerda que este canal no atiende emergencias en
curso. El teclado de respuesta se oculta y la conversación termina.

## 4. Ayuda y cancelación

### `/ayuda`

Funciona dentro o fuera de un reporte y no modifica su estado:

> 🤖 Galápagos Previene
>
> Reportar es fácil, solo 4 pasos:
> 1️⃣ Elige qué pasó
> 2️⃣ Envía fotos o videos
> 3️⃣ Comparte tu ubicación
> 4️⃣ Cuéntanos brevemente
>
> Comandos:
> /iniciar - Nuevo reporte
> /nuevo - Registrar otro reporte
> /cancelar - Cancelar el reporte actual
> /ayuda - Ver esta ayuda
>
> 🚨 Si es una emergencia, llama al 911.

### `/cancelar` con un borrador activo

> Cancelado ✅ No enviamos nada.
>
> Cuando quieras, escribe /nuevo.

El reporte y las evidencias no se borran; quedan auditados con estado y paso
`CANCELLED`. Se limpia la sesión y se oculta el teclado de respuesta.

### `/cancelar` sin un borrador activo

> No tienes ningún reporte en curso. Escribe /iniciar para empezar.

## 8. Inventario de elementos interactivos

### Botones inline

| Etiqueta visible | Valor interno | Paso válido |
|---|---|---|
| `🌋 Evento` | `kind:EVENT` | Selección de clase. |
| `⚠️ Incidente` | `kind:INCIDENT` | Selección de clase. |
| `🌧️ Lluvia` | `event:RAIN` | Selección de tipo de Evento. |
| `🌊 Tsunami` | `event:TSUNAMI` | Selección de tipo de Evento. |
| `🔥 Incendio` | `event:FIRE` | Selección de tipo de Evento. |
| `✅ Finalizar fotos y videos` | `media:finish` | Recepción de evidencias. |

### Teclado de respuesta

| Etiqueta visible | Función | Paso válido |
|---|---|---|
| `📍 Compartir mi ubicación` | Solicita a Telegram una ubicación con consentimiento. | Ubicación. |
