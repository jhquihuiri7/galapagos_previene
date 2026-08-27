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

    KIND -->|🌋 Evento| EVENT_TYPE["Elegir uno de los 10 eventos adversos"]
    KIND -->|⚠️ Incidente| MEDIA["Enviar evidencias"]
    EVENT_TYPE --> MEDIA

    MEDIA -->|Envío único de fotos, videos o documentos compatibles| MEDIA_OK["Guardar todo el envío"]
    MEDIA_OK -->|Carga cerrada automáticamente| LOCATION["Compartir ubicación"]
    MEDIA -->|Archivos enviados después del cierre| MEDIA_LATE["Aviso: la carga ya se cerró"]
    MEDIA_LATE --> LOCATION

    LOCATION -->|Ubicación válida| DESCRIPTION["Escribir descripción de 10+ caracteres"]
    LOCATION -->|Contenido o ubicación inválida| LOCATION
    DESCRIPTION -->|Descripción corta o no textual| DESCRIPTION
    DESCRIPTION -->|Texto válido| SUBMITTED["Confirmación de envío y aviso del 911"]

    START -.->|/cancelar durante el flujo| CANCELLED["Cancelar el reporte"]
    START -.->|/tutorial en cualquier momento| HELP["Mostrar el tutorial sin cambiar el estado"]
```

El reporte se considera enviado únicamente después de recibir una descripción
válida. Antes de eso permanece como borrador (`DRAFT`) en PostgreSQL.

## 2. Comandos disponibles

El menú de Telegram muestra estos cuatro comandos:

| Comando | Texto del menú | Efecto |
|---|---|---|
| `/iniciar` | Crear un reporte | Inicia el flujo. |
| `/nuevo` | Reportar algo más | Inicia el mismo flujo. |
| `/cancelar` | Cancelar el reporte | Cancela el borrador activo, si existe. |
| `/tutorial` | Ver tutorial | Muestra el tutorial sin alterar el reporte. |

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

**Botones inline, dos por fila**

- `🌊 Tsunami` · `🌧️ Lluvias intensas`
- `💧 Inundación` · `🌊 Oleaje`
- `🏜️ Sequía` · `🧪 Cont. química`
- `🚤 Acc. acuático` · `🔥 Inc. forestal`
- `🏗️ Colapso infra.` · `🌬️ Vendaval`

**Estado de conversación:** `CHOOSE_EVENT_TYPE`.

Cuando el usuario elige cualquiera de los diez tipos, el bot guarda la
selección y vuelve a editar ese mensaje:

> ✅ Evento: `{nombre del evento elegido}`
>
> 📸 Ahora envíame fotos o videos de lo que está pasando.
>
> Selecciónalos todos y envíalos juntos en un solo mensaje.

No hay botón: la carga es única y el bot avanza solo cuando la recibe.

**Siguiente estado:** `WAITING_MEDIA`.

### Paso 2B — Ruta Incidente

**Acción del usuario**

Pulsa `⚠️ Incidente`.

No se solicita un subtipo. El bot crea el borrador y edita el mensaje de
selección para mostrar:

> ✅ Incidente
>
> 📸 Ahora envíame fotos o videos de lo que está pasando.
>
> Selecciónalos todos y envíalos juntos en un solo mensaje.

No hay botón: la carga es única y el bot avanza solo cuando la recibe.

**Siguiente estado:** `WAITING_MEDIA`.

### Paso 3 — Registrar fotos y videos (una sola carga)

El usuario envía **una sola vez** todo su material. En ese envío puede incluir:

- una foto nativa de Telegram;
- un video nativo de Telegram;
- una imagen enviada como documento, si su MIME comienza con `image/`;
- un video enviado como documento, si su MIME comienza con `video/`;
- un álbum con varias fotos y videos seleccionados juntos.

El pie de foto, si existe, se almacena como metadato. No se descarga el archivo:
se conservan sus identificadores de Telegram.

**Cómo se detecta el fin de la carga**

Telegram no entrega un álbum como un único mensaje: envía un update por archivo,
todos con el mismo `media_group_id`. El bot guarda cada elemento en silencio y,
cuando pasan `MEDIA_GROUP_TIMEOUT_SECONDS` (2 segundos) sin recibir otro
elemento del mismo grupo, da por completa la carga. Un archivo suelto, sin
`media_group_id`, cierra la carga de inmediato.

No se confirma archivo por archivo. Al cerrarse la carga, el bot envía un único
mensaje:

> ✅ Recibí `{cantidad}` archivo(s).
>
> 📍 Ahora compárteme tu ubicación.

Ese mismo mensaje ya trae el teclado de ubicación, de modo que el paso avanza
sin ninguna acción adicional del usuario.

Si el envío supera `MAX_MEDIA_FILES` (**10** por defecto), el bot avisa una sola
vez y conserva los primeros archivos:

> Solo puedo guardar `{límite}` archivos; los demás no se cargaron.

Si se envían más archivos **después** de que la carga se cerró, no se agregan al
reporte:

> Ya recibí tus archivos. Ahora necesito tu ubicación.

Si se envía texto, audio, un documento con MIME no admitido u otro contenido
antes de cerrar la carga:

> 📸 Necesito una foto o video.

Si ese contenido llega después del cierre, el bot repite la solicitud de
ubicación:

> 📍 Usa el botón para compartir tu ubicación.

La implementación también contiene este mensaje defensivo para un archivo que
llegue al extractor pero no pueda clasificarse como imagen o video:

> Formato no válido. Envía una foto o video.

Si el envío no dejó ninguna evidencia registrada, el bot responde y sigue
esperando:

> Envíame al menos una foto o video.

### Paso 4 — Ubicación

Como el cierre de la carga ocurre fuera de un handler (mediante el temporizador
del álbum), la conversación permanece en `WAITING_MEDIA` hasta que llega la
ubicación; ese estado también atiende los mensajes de ubicación.

**Botón de teclado de respuesta**

- `📍 Compartir mi ubicación`

Telegram solicita el consentimiento del usuario antes de compartir la
ubicación. También es válida una ubicación elegida manualmente desde el mapa.

**Estado de conversación:** `WAITING_MEDIA` (atiende ubicaciones tras el cierre
de la carga).

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
> 🌿 Gracias por ayudar a cuidar Galápagos.
>
> 🚨 En caso de emergencia, llama al ECU 911.
>
> Escribe /nuevo para reportar algo más.

Por decisión de producto la confirmación no muestra el identificador interno
del reporte ni el conteo de archivos: no son datos útiles para el usuario en ese
momento. El aviso del 911 recuerda que este canal no atiende emergencias en
curso. El teclado de respuesta se oculta y la conversación termina.

## 4. Tutorial y cancelación

### `/tutorial`

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
> /tutorial - Ver el tutorial
>
> 🚨 Si es una emergencia, llama al 911.

### `/cancelar` con un borrador activo

> ✅ Cancelado. No enviamos nada.
>
> Cuando quieras, escribe /nuevo.

El reporte y las evidencias no se borran; quedan auditados con estado y paso
`CANCELLED`. Se limpia la sesión y se oculta el teclado de respuesta.

### `/cancelar` sin un borrador activo

> No tienes ningún reporte en curso. Escribe /iniciar para empezar.

## 5. Respuestas ante acciones fuera del paso esperado

| Situación | Respuesta visible | Resultado |
|---|---|---|
| Escribir en lugar de pulsar Evento/Incidente | `👆 Toca uno de los botones de arriba para continuar.` | Continúa en `CHOOSE_KIND`. |
| Escribir en lugar de elegir un tipo de evento | `👆 Toca uno de los botones de arriba para continuar.` | Continúa en `CHOOSE_EVENT_TYPE`. |
| Pulsar un botón viejo o que no pertenece al paso activo | Alerta: `Ese botón no corresponde al paso actual.` | No cambia de estado. |
| Callback de clase de reporte con valor inválido | Alerta: `Esa opción no es válida.` | Continúa en `CHOOSE_KIND`. |
| Callback de tipo de evento con valor inválido | Alerta: `Ese tipo de evento no es válido.` | Continúa en `CHOOSE_EVENT_TYPE`. |
| El tipo de evento válido no puede persistirse | Alerta: `No pudimos guardar esa opción. Intenta de nuevo.` | Continúa en `CHOOSE_EVENT_TYPE`. |
| Falta el identificador de la sesión durante una transición atendida | Alerta y mensaje: `Este reporte ya no está activo. Usa /iniciar.` | Limpia la sesión y termina la conversación. |
| Excepción no controlada con un mensaje al cual responder | `Hubo un problema. Intenta de nuevo o usa /iniciar.` | El detalle técnico solo queda en logs. |

Los callbacks con valores inválidos de las dos selecciones están bloqueados
normalmente por los patrones del enrutador; sus textos son protecciones
defensivas. Un callback distinto sí llega a la respuesta genérica de botón
fuera de paso cuando hay una conversación activa.

## 6. Estados y datos persistidos

| Estado de Telegram | Paso persistido | Qué espera del usuario |
|---|---|---|
| `CHOOSE_KIND` | Todavía no existe un reporte | Botón Evento o Incidente. |
| `CHOOSE_EVENT_TYPE` | `CHOOSE_EVENT_TYPE` | Uno de los 10 botones de evento. |
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
| `🌊 Tsunami` | `event:TSU` | Selección de tipo de Evento. |
| `🌧️ Lluvias intensas` | `event:LLI` | Selección de tipo de Evento. |
| `💧 Inundación` | `event:INU` | Selección de tipo de Evento. |
| `🌊 Oleaje` | `event:OLJ` | Selección de tipo de Evento. |
| `🏜️ Sequía` | `event:SEQ` | Selección de tipo de Evento. |
| `🧪 Cont. química` | `event:CQM` | Selección de tipo de Evento. |
| `🚤 Acc. acuático` | `event:AMA` | Selección de tipo de Evento. |
| `🔥 Inc. forestal` | `event:INF` | Selección de tipo de Evento. |
| `🏗️ Colapso infra.` | `event:COI` | Selección de tipo de Evento. |
| `🌬️ Vendaval` | `event:VDV` | Selección de tipo de Evento. |

### Teclado de respuesta

| Etiqueta visible | Función | Paso válido |
|---|---|---|
| `📍 Compartir mi ubicación` | Solicita a Telegram una ubicación con consentimiento. | Ubicación. |

## 9. Archivos responsables del flujo

- `app/bot.py`: registra comandos y handlers, y fuerza procesamiento secuencial.
- `app/handlers/commands.py`: inicio, reinicio, tutorial y cancelación.
- `app/handlers/report_flow.py`: mensajes, validaciones y transiciones.
- `app/keyboards.py`: etiquetas y organización de botones.
- `app/states.py`: estados en memoria y límite inicial de archivos.
- `app/services/telegram_media.py`: formatos aceptados y metadatos de evidencia.
- `app/repositories/reports.py`: creación, transición, cancelación y envío.
- `app/repositories/media.py`: contador, duplicados, límite y finalización.
- `schema.sql`: integridad permanente de reportes, pasos y evidencias.
- `tests/test_report_flow.py`, `tests/test_validations.py` y
  `tests/test_media_extraction.py`: contrato probado del recorrido.
