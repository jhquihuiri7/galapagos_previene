# Flujo de mensajes de Telegram — Galápagos Previene

Este documento describe la interacción que actualmente implementa el bot de
Telegram. Incluye los mensajes que ve el usuario, los botones disponibles, las
validaciones, las rutas de error y los cambios de estado del reporte.

> Fuente de verdad revisada: `app/bot.py`, `app/handlers/commands.py`,
> `app/handlers/report_flow.py`, `app/handlers/errors.py`, `app/keyboards.py`,
> `app/states.py`, `app/services/telegram_media.py`, repositorios, esquema SQL y
> pruebas. La API REST de `app/api/` es un consumidor externo y no agrega
> mensajes a la conversación de Telegram.

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
    DESCRIPTION -->|Texto válido| SUBMITTED["Confirmación con código y cantidad de archivos"]

    START -.->|/cancelar durante el flujo| CANCELLED["Cancelar el reporte"]
    START -.->|/ayuda en cualquier momento| HELP["Mostrar ayuda sin cambiar el estado"]
```

El reporte se considera enviado únicamente después de recibir una descripción
válida. Antes de eso permanece como borrador (`DRAFT`) en PostgreSQL.

## 2. Comandos disponibles

El menú de Telegram muestra estos cuatro comandos:

| Comando | Texto del menú | Efecto |
|---|---|---|
| `/iniciar` | Iniciar un nuevo reporte | Inicia el flujo. |
| `/nuevo` | Registrar otro reporte | Inicia el mismo flujo. |
| `/cancelar` | Cancelar el reporte actual | Cancela el borrador activo, si existe. |
| `/ayuda` | Mostrar instrucciones | Muestra ayuda sin alterar el reporte. |

`/start` también inicia el flujo, aunque no aparece en el menú configurado por
el bot. Es el comando que Telegram usa normalmente al pulsar **Iniciar** por
primera vez.

Los comandos `/start`, `/iniciar` y `/nuevo` pueden utilizarse incluso durante
una conversación activa. En ese caso se abandona el recorrido actual, se
cancela lógicamente el borrador anterior y se comienza desde la selección del
tipo de reporte.

## 3. Flujo principal, mensaje por mensaje

### Paso 1 — Iniciar o reiniciar

**Acción del usuario**

Envía `/start`, `/iniciar` o `/nuevo`.

Si ya tenía un borrador activo, primero recibe un mensaje independiente:

> El borrador anterior fue cancelado.

Ese mensaje también ordena ocultar cualquier teclado de respuesta anterior.
Después, tanto para un usuario nuevo como para uno que reinició, el bot envía:

> 🌿 Bienvenido a Galápagos Previene.
>
> ¿Qué deseas reportar?

**Botones inline, en una misma fila**

- `🌋 Evento`
- `⚠️ Incidente`

**Estado de conversación:** `CHOOSE_KIND`.

### Paso 2A — Ruta Evento

**Acción del usuario**

Pulsa `🌋 Evento`.

El bot crea el borrador y edita el mensaje de selección para mostrar:

> Seleccionaste Evento. ¿Qué tipo de evento deseas reportar?

**Botones inline, uno por fila**

- `🌧️ Lluvia`
- `🌊 Tsunami`
- `🔥 Incendio`

**Estado de conversación:** `CHOOSE_EVENT_TYPE`.

Cuando el usuario elige cualquiera de los tres tipos, el bot guarda la
selección y vuelve a editar ese mensaje:

> Tipo de evento registrado.
>
> Ahora envía una o más fotos o videos como evidencia. También puedes enviarlos como documentos.

Inmediatamente envía un segundo mensaje:

> Cuando termines, pulsa el botón siguiente.

**Botón inline**

- `✅ Finalizar fotos y videos`

**Siguiente estado:** `WAITING_MEDIA`.

### Paso 2B — Ruta Incidente

**Acción del usuario**

Pulsa `⚠️ Incidente`.

No se solicita un subtipo. El bot crea el borrador y edita el mensaje de
selección para mostrar:

> Seleccionaste Incidente.
>
> Envía una o más fotos o videos como evidencia. También puedes enviarlos como documentos.

Después envía un segundo mensaje:

> Cuando termines, pulsa el botón siguiente.

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

> ✅ Archivo registrado correctamente.
> Archivos registrados: `{cantidad}` de `{límite}`.
>
> Puedes enviar más fotos o videos.

El mensaje conserva el botón:

- `✅ Finalizar fotos y videos`

`{límite}` corresponde a `MAX_MEDIA_FILES`; el valor predeterminado es **10**.

Si Telegram vuelve a entregar el mismo mensaje y el archivo ya había sido
registrado, el bot responde:

> ℹ️ Este archivo ya estaba registrado.
> Archivos registrados: `{cantidad}` de `{límite}`.
>
> Puedes enviar más fotos o videos.

Si ya se alcanzó el máximo configurado:

> Ya alcanzaste el máximo de `{límite}` archivos. Pulsa «Finalizar fotos y videos» para continuar.

Si se envía texto, audio, un documento con MIME no admitido u otro contenido
en este paso:

> Envía una foto o video compatible, o pulsa «Finalizar fotos y videos».

La implementación también contiene este mensaje defensivo para un archivo que
llegue al extractor pero no pueda clasificarse como imagen o video:

> Ese archivo no es una imagen o un video compatible. Intenta enviarlo como foto, video o documento con un tipo MIME válido.

Todos estos casos mantienen el estado `WAITING_MEDIA` y vuelven a mostrar el
botón de finalización.

### Paso 4 — Finalizar evidencias

**Acción del usuario**

Pulsa `✅ Finalizar fotos y videos`.

Si todavía no registró ninguna evidencia, Telegram muestra una alerta:

> Debes registrar al menos una foto o video antes de continuar.

El usuario permanece en `WAITING_MEDIA`.

Si existe al menos una evidencia, el bot edita el mensaje que contenía el
botón:

> ✅ Evidencias finalizadas: `{cantidad}` archivo(s) registrado(s).

Después envía un nuevo mensaje:

> Ahora comparte la ubicación del evento o incidente. También puedes seleccionarla manualmente desde el mapa de Telegram.

**Botón de teclado de respuesta**

- `📍 Compartir mi ubicación`

Telegram solicita el consentimiento del usuario antes de compartir la
ubicación. También es válida una ubicación elegida manualmente desde el mapa.

**Siguiente estado:** `WAITING_LOCATION`.

### Paso 5 — Compartir la ubicación

Al recibir una ubicación válida, el bot guarda latitud, longitud y precisión,
oculta el teclado de ubicación y responde:

> 📍 Ubicación registrada.
>
> Escribe una descripción clara del evento o incidente (mínimo 10 caracteres).

**Siguiente estado:** `WAITING_DESCRIPTION`.

Las coordenadas deben ser numéricas y finitas, con latitud entre `-90` y `90`
y longitud entre `-180` y `180`.

Si Telegram entrega un objeto de ubicación con coordenadas inválidas:

> La ubicación no es válida. Intenta compartirla nuevamente.

Si la ubicación es válida pero ya no puede guardarse en el paso actual:

> No se pudo guardar la ubicación en el paso actual. Intenta compartirla nuevamente o usa /iniciar.

Si el usuario envía texto, archivos u otro contenido en lugar de una ubicación:

> Necesito una ubicación de Telegram. Usa el botón o selecciónala manualmente desde el mapa.

En los tres casos se mantiene `WAITING_LOCATION` y se vuelve a mostrar el botón
`📍 Compartir mi ubicación`.

### Paso 6 — Escribir la descripción

El usuario debe enviar un mensaje de texto con al menos 10 caracteres después
de quitar los espacios del principio y del final. Los espacios internos se
conservan.

Si el texto tiene menos de 10 caracteres:

> La descripción debe contener al menos 10 caracteres. Por favor, intenta nuevamente.

Si envía una foto, video, ubicación u otro contenido no textual:

> La descripción debe ser un mensaje de texto de al menos 10 caracteres.

Ambas respuestas mantienen el estado `WAITING_DESCRIPTION`.

### Paso 7 — Confirmación final

Con una descripción válida, el bot vuelve a comprobar la integridad del
reporte, lo marca como enviado (`SUBMITTED`), limpia la sesión temporal y
responde:

> ✅ La información se guardó correctamente.
>
> Código del reporte: `{CÓDIGO_DE_8_CARACTERES}`
> Archivos registrados: `{cantidad}`
>
> Gracias por contribuir con Galápagos Previene.
>
> Usa /nuevo para registrar otro reporte.

El código se forma con los primeros ocho caracteres hexadecimales del UUID del
reporte, sin guiones y en mayúsculas. El teclado de respuesta se oculta y la
conversación termina.

## 4. Ayuda y cancelación

### `/ayuda`

Funciona dentro o fuera de un reporte y no modifica su estado:

> 🤖 Galápagos Previene
>
> Comandos disponibles:
>
> /iniciar - Iniciar un nuevo reporte
> /nuevo - Registrar otro reporte
> /cancelar - Cancelar el reporte actual
> /ayuda - Mostrar instrucciones
>
> Para registrar un reporte deberás indicar el tipo, adjuntar una o más fotos o videos, compartir una ubicación y escribir una descripción.

### `/cancelar` con un borrador activo

> ✅ El reporte actual fue cancelado. Puedes usar /nuevo cuando quieras comenzar otro.

El reporte y las evidencias no se borran; quedan auditados con estado y paso
`CANCELLED`. Se limpia la sesión y se oculta el teclado de respuesta.

### `/cancelar` sin un borrador activo

> No tienes un reporte activo para cancelar. Usa /iniciar para comenzar.

## 5. Respuestas ante acciones fuera del paso esperado

| Situación | Respuesta visible | Resultado |
|---|---|---|
| Escribir en lugar de pulsar Evento/Incidente | `Selecciona Evento o Incidente usando los botones del mensaje.` | Continúa en `CHOOSE_KIND`. |
| Escribir en lugar de elegir un tipo de evento | `Selecciona Lluvia, Tsunami o Incendio usando los botones.` | Continúa en `CHOOSE_EVENT_TYPE`. |
| Pulsar un botón viejo o que no pertenece al paso activo | Alerta: `Ese botón no corresponde al paso actual.` | No cambia de estado. |
| Callback de clase de reporte con valor inválido | Alerta: `Opción de reporte inválida.` | Continúa en `CHOOSE_KIND`. |
| Callback de tipo de evento con valor inválido | Alerta: `Tipo de evento inválido.` | Continúa en `CHOOSE_EVENT_TYPE`. |
| El tipo de evento válido no puede persistirse | Alerta: `No se pudo guardar esa selección. Intenta nuevamente.` | Continúa en `CHOOSE_EVENT_TYPE`. |
| Falta el identificador de la sesión durante una transición atendida | Alerta: `La sesión del reporte ya no está activa.` y mensaje `La sesión del reporte terminó. Usa /iniciar para comenzar de nuevo.` | Limpia la sesión y termina la conversación. |
| Excepción no controlada con un mensaje al cual responder | `Ocurrió un error inesperado al procesar tu solicitud. Intenta nuevamente o usa /iniciar para comenzar otro reporte.` | El detalle técnico solo queda en logs. |

Los callbacks con valores inválidos de las dos selecciones están bloqueados
normalmente por los patrones del enrutador; sus textos son protecciones
defensivas. Un callback distinto sí llega a la respuesta genérica de botón
fuera de paso cuando hay una conversación activa.

## 6. Estados y datos persistidos

| Estado de Telegram | Paso persistido | Qué espera del usuario |
|---|---|---|
| `CHOOSE_KIND` | Todavía no existe un reporte | Botón Evento o Incidente. |
| `CHOOSE_EVENT_TYPE` | `CHOOSE_EVENT_TYPE` | Botón Lluvia, Tsunami o Incendio. |
| `WAITING_MEDIA` | `WAITING_MEDIA` | Una o más evidencias y luego finalizar. |
| `WAITING_LOCATION` | `WAITING_LOCATION` | Una ubicación de Telegram. |
| `WAITING_DESCRIPTION` | `WAITING_DESCRIPTION` | Texto de al menos 10 caracteres. |
| Fin de conversación | `COMPLETED` | El reporte quedó `SUBMITTED`. |
| Fin por cancelación | `CANCELLED` | El reporte quedó `CANCELLED`. |

La selección Evento/Incidente es especial: el borrador se crea al pulsar uno de
los botones, no al ejecutar el comando inicial. Un Evento exige subtipo; un
Incidente conserva `event_type_id = NULL`.

## 7. Comportamiento relevante para la experiencia de usuario

- Solo puede existir un borrador activo por usuario. Iniciar otro cancela el
  anterior automáticamente.
- El flujo se identifica por usuario y chat (`per_user=True`, `per_chat=True`).
- Los mensajes se procesan secuencialmente. En un álbum, cada elemento produce
  su propia confirmación y contador.
- El botón de finalizar no espera a que termine un álbum por temporizador. El
  avance ocurre exclusivamente cuando el callback se procesa en la secuencia.
- No hay botones **Atrás**, **Cambiar tipo**, **Eliminar evidencia** o
  **Confirmar antes de enviar**. Para corregir una elección anterior hay que
  usar `/iniciar`, `/nuevo` o `/cancelar` y comenzar otra vez.
- Después de finalizar las evidencias ya no se aceptan archivos adicionales;
  se interpretan como contenido inesperado del paso de ubicación o descripción.
- Los comandos desconocidos no tienen un manejador propio y, por tanto, no
  generan una respuesta. Los mensajes normales enviados fuera de una
  conversación tampoco generan respuesta.
- El estado del borrador se guarda en PostgreSQL, pero la conversación de
  `python-telegram-bot` y el UUID activo viven solo en memoria: no hay una
  persistencia ni rutina de rehidratación configurada. Tras reiniciar el proceso,
  el usuario debe usar `/iniciar` o `/nuevo`; esto cancelará el borrador previo.
- El bot está diseñado para chat privado, aunque el código no aplica un filtro
  explícito que rechace grupos. La configuración documentada de BotFather
  recomienda deshabilitar su incorporación a grupos.

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

## 9. Archivos responsables del flujo

- `app/bot.py`: registra comandos y handlers, y fuerza procesamiento secuencial.
- `app/handlers/commands.py`: inicio, reinicio, ayuda y cancelación.
- `app/handlers/report_flow.py`: mensajes, validaciones y transiciones.
- `app/keyboards.py`: etiquetas y organización de botones.
- `app/states.py`: estados en memoria y límite inicial de archivos.
- `app/services/telegram_media.py`: formatos aceptados y metadatos de evidencia.
- `app/repositories/reports.py`: creación, transición, cancelación y envío.
- `app/repositories/media.py`: contador, duplicados, límite y finalización.
- `schema.sql`: integridad permanente de reportes, pasos y evidencias.
- `tests/test_report_flow.py`, `tests/test_validations.py` y
  `tests/test_media_extraction.py`: contrato probado del recorrido.
