// Guion del chat, fiel a docs/flujo-mensajes-telegram.md
// Los botones inline NO producen mensaje del usuario: el bot edita el suyo.
//
// Los tiempos están atados al voiceover de public/VO-final.mp3 (64,10 s): cada
// evento se declara con el segundo absoluto del video en que debe verse, para
// poder compararlo directo con la locución. La tabla vive en
// docs/guion-video-flujo-telegram.md.

import { f, FPS } from "./timing";

export type Btn = string;

export { FPS };

/** Segundo en que el chat entra en pantalla; antes va la intro. */
const INTRO_SECONDS = 5.7;

/** Segundo en que termina el video; el voiceover dura 64,10 s. */
const TOTAL_SECONDS = 64.15;

export const INTRO_DURATION = Math.round(INTRO_SECONDS * FPS);
export const TOTAL_DURATION = Math.round(TOTAL_SECONDS * FPS);

/**
 * Frame local del chat a partir del segundo absoluto del video.
 * El chat arranca en INTRO_DURATION, así que ese offset se descuenta.
 */
const s = (second: number) => Math.round(second * FPS) - INTRO_DURATION;

/**
 * Frames que la hoja de adjuntos tarda desde que se abre hasta que se pulsa
 * Enviar (ver SEND en AttachSheet.tsx). El álbum debe entrar 8 s después del
 * evento «attach»; si se mueve uno hay que mover el otro.
 */
export const SHEET_SEND = f(240);

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
  ["🏜️ Sequía", "🧪 Cont. química"],
  ["🚤 Acc. acuático", "🔥 Inc. forestal"],
  ["🏗️ Colapso infra.", "🌬️ Vendaval"],
];

const MEDIA_PROMPT =
  "📸 Ahora envíame fotos o videos de lo que está pasando.\n\nSelecciónalos todos y envíalos juntos en un solo mensaje.";

export const events: Event[] = [
  { t: "commands", at: s(6.1), show: true },
  { t: "commands", at: s(8.7), show: false },
  { t: "msg", at: s(8.9), id: "u1", from: "user", text: "/iniciar" },

  {
    t: "msg",
    at: s(9.7),
    id: "b1",
    from: "bot",
    text:
      "🌿 ¡Hola! Bienvenido a Galápagos Previene.\n\nAquí puedes avisarnos de algo que esté pasando en las islas.\n\n¿Qué quieres reportar?",
    buttons: [["🌋 Evento", "⚠️ Incidente"]],
  },

  // Toque de botón inline -> el bot edita SU mensaje, no hay burbuja del usuario
  { t: "tap", at: s(16.2), id: "b1", label: "🌋 Evento" },
  {
    t: "edit",
    at: s(16.9),
    id: "b1",
    text: "¿Qué tipo de evento quieres reportar?",
    buttons: EVENT_BUTTONS,
  },

  { t: "tap", at: s(25.3), id: "b1", label: "🔥 Inc. forestal" },
  { t: "edit", at: s(26.9), id: "b1", text: "Evento: Incendio forestal ✓\n\n" + MEDIA_PROMPT },

  // Selección de 3 fotos en la galería del iPhone
  { t: "attach", at: s(30.4) },
  // Álbum: un update por archivo, cierre por temporizador de 2 s
  {
    t: "msg",
    at: s(30.4) + SHEET_SEND,
    id: "u4",
    from: "user",
    text: "",
    album: ["fuego-columna", "fuego-quemado", "fuego-personas"],
  },
  {
    t: "msg",
    at: s(39.7),
    id: "b4",
    from: "bot",
    text: "✅ Recibí 3 archivo(s).\n\n📍 Ahora compárteme tu ubicación.",
  },
  { t: "keyboard", at: s(39.77), labels: ["📍 Compartir mi ubicación"] },

  {
    t: "msg",
    at: s(44.3),
    id: "u5",
    from: "user",
    text: "",
    location: true,
  },
  { t: "keyboard", at: s(44.37), labels: null },
  {
    t: "msg",
    at: s(44.9),
    id: "b5",
    from: "bot",
    text: "✅ Listo.\n\n✍️ Último paso: cuéntame brevemente qué ocurrió.",
  },

  {
    t: "msg",
    at: s(50.5),
    id: "u7",
    from: "user",
    text: "Humo denso en la zona alta de Santa Cruz, cerca del camino a Bellavista.",
  },
  {
    t: "msg",
    at: s(52.8),
    id: "b7",
    from: "bot",
    text:
      "✅ ¡Listo! Tu reporte fue enviado.\n\nGracias por ayudar a cuidar Galápagos 🌿\n\n🚨 En caso de emergencia, llama al ECU 911.\n\nEscribe /nuevo para reportar algo más.",
  },

];

export const CHAT_DURATION = TOTAL_DURATION - INTRO_DURATION;

export const COMMAND_MENU: [string, string][] = [
  ["/iniciar", "Crear un reporte"],
  ["/nuevo", "Reportar algo más"],
  ["/cancelar", "Cancelar el reporte"],
  ["/tutorial", "Ver tutorial"],
];
