/**
 * Rollo de cámara del iPhone. Las tres primeras son del evento reportado
 * (incendio forestal) y son las que se seleccionan: en iOS la galería muestra
 * primero lo más reciente, y el usuario acaba de fotografiar el incendio.
 */
export type Photo = {
  id: string;
  /** Archivo dentro de public/galeria. */
  src: string;
  /** Color de respaldo mientras carga la imagen. */
  bg: string;
};

export const GALLERY: Photo[] = [
  { id: "fuego-columna", src: "galeria/fuego-columna.jpg", bg: "#9aa1a7" },
  { id: "fuego-quemado", src: "galeria/fuego-quemado.jpg", bg: "#3b3a35" },
  { id: "fuego-personas", src: "galeria/fuego-personas.jpg", bg: "#7a8896" },
  { id: "tortuga", src: "galeria/tortuga.jpg", bg: "#4a6b32" },
  { id: "iguana", src: "galeria/iguana.jpg", bg: "#2b7fae" },
  { id: "calle", src: "galeria/calle.jpg", bg: "#6f9c4b" },
  { id: "muelle", src: "galeria/muelle.jpg", bg: "#4a7d9b" },
  { id: "comida", src: "galeria/comida.jpg", bg: "#3f6b5e" },
  { id: "cactus", src: "galeria/cactus.jpg", bg: "#5f7fa8" },
];

/** Las tres que se seleccionan, en el orden en que se tocan. */
export const PICKED = ["fuego-columna", "fuego-quemado", "fuego-personas"] as const;

export const byId = (id: string): Photo => GALLERY.find((p) => p.id === id) ?? GALLERY[0];
