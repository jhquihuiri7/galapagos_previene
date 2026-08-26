// Guion del chat, fiel a docs/flujo-mensajes-telegram.md
// Los botones inline NO producen mensaje del usuario: el bot edita el suyo.

export type Btn = string;

/** Frame, dentro de la hoja de adjuntos, en que se pulsa Enviar. */
export const SHEET_SEND = 240;

export type Event =
  | {
      t: "msg";
      at: number;
      id: string;
      from: "user" | "bot";
      text: string;
      buttons?: Btn[][];
      album?: string[];
      location?: boolean;
    }
  | { t: "attach"; at: number }
  | { t: "edit"; at: number; id: string; text: string; buttons?: Btn[][] }
  | { t: "tap"; at: number; id: string; label: Btn }
  | { t: "service"; at: number; id: string; text: string }
  | { t: "keyboard"; at: number; labels: Btn[] | null }
  | { t: "commands"; at: number; show: boolean };

const EVENT_BUTTONS: Btn[][] = [
  ["🌊 Tsunami", "🌧️ Lluvias intensas"],
  ["💧 Inundación", "🌊 Oleaje"],
  ["🏜️ Sequía", "🚤 Acc. acuático"],
  ["🐛 Plaga", "🔥 Inc. forestal"],
  ["🏗️ Colapso infra.", "🌬️ Vendaval"],
];

const MEDIA_PROMPT =
  "📸 Ahora envíame fotos o videos de lo que está pasando.\n\nSelecciónalos todos y envíalos juntos en un solo mensaje.";

let cursor = 0;
const at = (gap: number) => (cursor += gap);

export const events: Event[] = [
  { t: "commands", at: at(20), show: true },
  { t: "commands", at: at(70), show: false },
  { t: "msg", at: at(6), id: "u1", from: "user", text: "/iniciar" },

  {
    t: "msg",
    at: at(80),
    id: "b1",
    from: "bot",
    text:
      "🌿 ¡Hola! Bienvenido a Galápagos Previene.\n\nAquí puedes avisarnos de algo que esté pasando en las islas.\n\n¿Qué quieres reportar?",
    buttons: [["🌋 Evento", "⚠️ Incidente"]],
  },

  // Toque de botón inline -> el bot edita SU mensaje, no hay burbuja del usuario
  { t: "tap", at: at(110), id: "b1", label: "🌋 Evento" },
  {
    t: "edit",
    at: at(42),
    id: "b1",
    text: "¿Qué tipo de evento quieres reportar?",
    buttons: EVENT_BUTTONS,
  },

  { t: "tap", at: at(210), id: "b1", label: "🔥 Inc. forestal" },
  { t: "edit", at: at(40), id: "b1", text: "Evento: Incendio forestal ✓\n\n" + MEDIA_PROMPT },

  // Selección de 3 fotos en la galería del iPhone
  { t: "attach", at: at(80) },
  // Álbum: un update por archivo, cierre por temporizador de 2 s
  {
    t: "msg",
    at: at(SHEET_SEND),
    id: "u4",
    from: "user",
    text: "",
    album: ["fuego-columna", "fuego-quemado", "fuego-personas"],
  },
  {
    t: "msg",
    at: at(75),
    id: "b4",
    from: "bot",
    text: "✅ Recibí 3 archivo(s).\n\n📍 Ahora compárteme tu ubicación.",
  },
  { t: "keyboard", at: at(2), labels: ["📍 Compartir mi ubicación"] },

  {
    t: "msg",
    at: at(130),
    id: "u5",
    from: "user",
    text: "",
    location: true,
  },
  { t: "keyboard", at: at(2), labels: null },
  {
    t: "msg",
    at: at(50),
    id: "b5",
    from: "bot",
    text: "✅ Listo.\n\n✍️ Último paso: cuéntame brevemente qué ocurrió.",
  },

  {
    t: "msg",
    at: at(135),
    id: "u7",
    from: "user",
    text: "Humo denso en la zona alta de Santa Cruz, cerca del camino a Bellavista.",
  },
  {
    t: "msg",
    at: at(60),
    id: "b7",
    from: "bot",
    text:
      "✅ ¡Listo! Tu reporte fue enviado.\n\nGracias por ayudar a cuidar Galápagos 🌿\n\n🚨 En caso de emergencia, llama al ECU 911.\n\nEscribe /nuevo para reportar algo más.",
  },

];

export const CHAT_DURATION = cursor + 240;

export const COMMAND_MENU: [string, string][] = [
  ["/iniciar", "Crear un reporte"],
  ["/nuevo", "Reportar algo más"],
  ["/cancelar", "Cancelar el reporte"],
  ["/tutorial", "Ver tutorial"],
];
