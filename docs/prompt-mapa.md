# Prompt para generar el visor de mapa

Copia el bloque siguiente. Antes de enviarlo reemplaza `<STACK>` por la
tecnología en la que se construirá (Django + Leaflet, Node/Express + MapLibre,
FastAPI + React…). **No pegues la API key en el prompt**: deja el marcador y
entrégala aparte, para que viva en una variable de entorno del servidor.

---

```text
Construye un visor de mapa (<STACK>) que muestre los reportes ciudadanos de
"Galápagos Previene": emergencias y eventos naturales reportados por la
población de las islas Galápagos a través de un bot de Telegram, con foto o
video, ubicación GPS y descripción.

## Origen de los datos

Una API REST de solo lectura, ya desplegada, en http://127.0.0.1:8080
Requiere la cabecera `Authorization: Bearer <API_KEY>` en todas las rutas /v1.
Esquema OpenAPI disponible en /openapi.json

Endpoints relevantes:

  GET /v1/reports?since=&cursor_id=&limit=   Lista incremental (máx. 200/página)
  GET /v1/reports/{id}                        Detalle
  GET /v1/media/{media_id}/content            Bytes de una foto o video
  GET /v1/event-types                         Catálogo: código, nombre y familia

Un reporte tiene esta forma:

{
  "id": "3f2a…",
  "reporter_id": "8c11…",           // UUID anónimo; NO mostrar en la interfaz
  "report_kind": "EVENT",           // "EVENT" o "INCIDENT"
  "event_type_code": "LLI",         // código de 3 letras del catálogo | null
  "event_type_name": "Lluvias intensas",
  "latitude": -0.7436,
  "longitude": -90.3134,
  "location_accuracy": 12.5,        // metros; puede ser null
  "description": "Lluvia intensa en la vía a Bellavista.",
  "media": [
    { "id": "b4d7…", "media_type": "PHOTO",
      "content_url": "/v1/media/b4d7…/content",
      "mime_type": "image/jpeg", "file_size": 204800,
      "width": 1280, "height": 853, "duration_seconds": null,
      "caption": "Vía inundada", "created_at": "2026-08-06T12:00:00Z" }
  ],
  "created_at": "…", "updated_at": "…", "submitted_at": "2026-08-06T12:00:00Z"
}

En un reporte INCIDENT, `event_type_code` y `event_type_name` son null: un
incidente es una categoría distinta, no un cuarto tipo de evento.

## Restricciones de arquitectura — léelas antes de diseñar

Estas tres condicionan toda la implementación. Una solución de solo-frontend
NO funciona:

1. LA API KEY NO PUEDE VIVIR EN EL NAVEGADOR. Cualquiera que abra las
   herramientas de desarrollo la leería y tendría acceso directo a todos los
   reportes. El visor DEBE tener un backend propio que guarde la clave en una
   variable de entorno del servidor y actúe de proxy hacia la API.

2. LA API NO TIENE CORS HABILITADO y escucha solo en 127.0.0.1. Un fetch desde
   el navegador hacia ella fallará. Todas las peticiones pasan por tu backend.

3. LAS IMÁGENES NO SE PUEDEN PONER DIRECTAMENTE EN UN <img src>. La descarga
   exige la cabecera Authorization, y una etiqueta <img> no la envía: recibirás
   401. Expón en tu backend una ruta propia (por ejemplo
   /media/{media_id}) que reenvíe la petición añadiendo la cabecera y
   retransmita los bytes en streaming; el <img> apunta a esa ruta tuya. No
   cargues los archivos enteros en memoria: un video puede pesar decenas de MB.

Arquitectura resultante:

  navegador  ──►  backend del visor  ──►  API de reportes  ──►  Telegram
              (mapa)   (guarda la key,        (127.0.0.1:8080)
                        proxy de medios)

## Ingesta de los datos

Recorre /v1/reports con su cursor incremental: guarda el objeto `next` de cada
página y vuelve a pedir con `since` + `cursor_id` hasta que `next` sea null.
Cachea los reportes en tu backend (base de datos o caché en memoria con TTL) y
refresca cada 1–5 minutos. No vuelvas a descargar el catálogo completo en cada
carga de página, y nunca hagas que el navegador pida los reportes de uno en
uno.

Ingiere con upsert por `id`: un reporte modificado reaparece en una página
posterior.

## El mapa

Centro inicial: -0.62, -90.50 (archipiélago de Galápagos), zoom ~8.
Límites aproximados: latitud -1.5 a 0.8, longitud -92.1 a -89.2.
Ajusta el encuadre a los datos reales al cargar (fitBounds), pero sin alejar
más allá de esos límites.

Usa teselas de OpenStreetMap o similar; incluye la atribución obligatoria del
proveedor. Ten en cuenta que las islas están rodeadas de océano: un mapa
demasiado alejado será casi todo azul, así que el encuadre por defecto debe
ceñirse a donde hay reportes.

### Codificación visual — respétala tal cual

El COLOR codifica el grupo del evento. La FORMA codifica la clase de reporte.
Son dos dimensiones distintas del dato y no deben mezclarse:

  El catálogo activo tiene diez eventos agrupados en seis familias. En un mapa
  todos los marcadores se ven a la vez y en cualquier combinación, así que el
  color debe distinguirse por pares en TODAS las parejas posibles, no solo
  entre vecinos de una leyenda. Seis colores no superan esa prueba, ni la
  superan cuatro: medido con el validador, el peor par de una paleta de cuatro
  cae a ΔE 1.9 con daltonismo y a 9.8 incluso con visión normal, por debajo del
  piso de 15.

  Por eso el color codifica un agrupamiento de TRES grandes grupos, que sí está
  validado en claro y en oscuro, y la familia y el código concretos se leen en
  la etiqueta, el tooltip y el filtro:

    Natural       Oceanográfico, Hidrometeorológico   #2a78d6 (azul)
                  → TSU, OLJ, LLI, INU, SEQ, VDV      · oscuro: #3987e5

    Antrópico     Tecnológico, Fallo estructural      #eb6834 (naranja)
                  → AMA, COI                          · oscuro: #d95926

    Ambiental     Ambiental, Biológico                #1baf7a (aqua)
    y biológico   → CQM, INF                          · oscuro: #199e70

    (sin tipo, es decir INCIDENT)                     gris neutro

  Un reporte histórico puede traer un código retirado (ERV, PLG, SIS, DES o
  CAD). Trátalo por su familia igual que a los demás: los cinco caen en
  «Natural» salvo PLG, que es Biológico.

  No añadas un cuarto color para partir estos grupos: cualquier cuarto tono
  rompe el piso de separación en modo claro o en oscuro. Si hace falta más
  detalle visual, usa el filtro por familia o divide el mapa en varios paneles
  (uno por familia), nunca más colores.

  Clase de reporte (forma del marcador):
    EVENT     círculo
    INCIDENT  rombo (o triángulo), en gris neutro

Reglas obligatorias, no opcionales:

- CADA MARCADOR LLEVA EL CÓDIGO DE TRES LETRAS COMO ETIQUETA O ICONO, ADEMÁS
  DEL COLOR. El color solo distingue los tres grandes grupos; la familia y el
  evento concreto SIEMPRE se leen en texto. No es un detalle estético: sin eso
  el mapa pierde siete de los diez tipos.
- El aqua queda por debajo de 3:1 sobre la superficie clara (2.74:1), así que
  en modo claro esas etiquetas visibles son obligatorias, no opcionales.
- Cada marcador lleva un anillo de 2px del color de la superficie a su
  alrededor. Resuelve dos problemas a la vez: separa los marcadores que se
  solapan y garantiza que se distingan sobre teselas de cualquier tono.
- Leyenda siempre visible, con el cuadro de color JUNTO al nombre escrito del
  grupo, y debajo la lista de familias que contiene. La identidad nunca puede
  depender solo del color.
- Un filtro por familia (las seis) y otro por evento (los diez) en una fila
  sobre el mapa. Filtrar NO puede repintar lo que queda: el color sigue al
  grupo del reporte, nunca a su posición en la lista.
- Marcadores de al menos 8px. El texto (etiquetas, popups, leyenda) va en
  color de texto normal, nunca en el color de la serie.
- Modo oscuro seleccionado, con los valores indicados arriba y teselas
  oscuras. No es una inversión automática del modo claro.

### Interacción

- Agrupa los marcadores cercanos en clusters al alejar el zoom, y expándelos al
  acercar. Sin esto, los reportes de un mismo punto se tapan entre sí.
- Al pulsar un marcador, abre un panel o popup con: tipo de evento, fecha de
  envío en zona horaria de Galápagos (UTC-6), descripción completa, y las
  miniaturas de las evidencias. Al pulsar una miniatura, ábrela a tamaño
  completo; los videos con un reproductor con controles.
- Si `location_accuracy` viene informado, dibuja un círculo translúcido de ese
  radio en metros alrededor del punto: comunica que la ubicación es aproximada.
- Filtros en una sola fila sobre el mapa: por tipo de evento, por clase de
  reporte y por rango de fechas. Los filtros no deben repintar los colores de
  lo que sobrevive al filtro — el color pertenece al tipo de evento, no a su
  posición en una lista.
- Muestra el número de reportes visibles con los filtros aplicados.
- Ofrece una vista de tabla alternativa con los mismos datos, ordenable por
  fecha y tipo. Es requisito de accesibilidad: el mapa no puede ser la única
  forma de leer la información.

### Privacidad

No muestres `reporter_id` en la interfaz. No hay nombres ni identificadores de
Telegram en los datos, y así debe seguir siendo. Si añades exportación de
datos, que no incluya ese campo.

## Entregable

1. El backend del visor: proxy autenticado hacia la API, caché de reportes con
   el cursor incremental, y la ruta de streaming de evidencias.
2. La página del mapa con la codificación visual, los clusters, los popups y
   los filtros descritos.
3. La vista de tabla alternativa.
4. Modo claro y oscuro.
5. Manejo de errores visible para el usuario: qué se muestra si la API no
   responde, si no hay reportes en el rango filtrado, o si una evidencia ya no
   está disponible (la API devuelve 404 cuando Telegram dejó de conservarla).
6. Un README con las variables de entorno necesarias y cómo levantarlo.

Antes de escribir el código completo, propón el diseño: cómo cachearás los
reportes, cómo estructurarás el proxy de medios y qué librería de mapas usarás
y por qué. Después de implementarlo, ábrelo y verifica visualmente que los
marcadores no se solapan de forma ilegible y que la leyenda es correcta.
```
