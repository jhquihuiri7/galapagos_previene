import React from "react";
import { Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { tg } from "./theme";
import { GALLERY, PICKED } from "./photos";
import { CAMERA_DURATION } from "./Camera";
import { f } from "./timing";

/**
 * Hoja de adjuntos de Telegram para iOS: sube desde abajo, muestra el rollo de
 * cámara en tres columnas y marca cada foto con un círculo numerado.
 */

// Fases relativas al inicio de la hoja
const OPEN = 0;
/** Se toca la celda de cámara; la pantalla de cámara vive en Camera.tsx. */
export const CAMERA_TAP = f(24);
export const CAMERA_OPEN = CAMERA_TAP + f(10);
/** La primera foto llega de la cámara; las otras dos, de la galería. */
const PICK = [
  CAMERA_OPEN + CAMERA_DURATION,
  CAMERA_OPEN + CAMERA_DURATION + f(22),
  CAMERA_OPEN + CAMERA_DURATION + f(40),
];
const SEND = PICK[2] + f(26);
const CLOSE = SEND + f(14);
export const SHEET_DURATION = CLOSE + f(22);
/** Alto aproximado de la hoja; el chat se desplaza para no quedar tapado. */
export const SHEET_HEIGHT = 800;
export const SHEET_CLOSE = CLOSE;
export const SHEET_RISE = f(20);

/** Cuánto sube la lista del chat mientras la hoja está abierta (0 a 1). */
export const sheetProgress = (rel: number) => {
  const up = Math.max(0, Math.min(1, rel / SHEET_RISE));
  const down = Math.max(0, Math.min(1, (rel - CLOSE) / f(12)));
  return Math.max(0, up - down);
};

const SheetPhoto: React.FC<{ index: number; order: number | null; frame: number }> = ({
  index,
  order,
  frame,
}) => {
  const photo = GALLERY[index];
  const pickedAt = order !== null ? PICK[order] : null;
  const picked = pickedAt !== null && frame >= pickedAt;
  const t = picked ? Math.min(1, (frame - (pickedAt as number)) / f(8)) : 0;

  return (
    <div
      style={{
        position: "relative",
        aspectRatio: "1 / 1",
        borderRadius: 6,
        overflow: "hidden",
        background: photo.bg,
        transform: `scale(${interpolate(t, [0, 1], [1, 0.92])})`,
      }}
    >
      <Img
        src={staticFile(photo.src)}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
      />
      {picked ? (
        <>
          <div
            style={{
              position: "absolute",
              inset: 0,
              border: `4px solid ${tg.link}`,
              borderRadius: 6,
              opacity: t,
            }}
          />
          <div
            style={{
              position: "absolute",
              top: 10,
              right: 10,
              width: 44,
              height: 44,
              borderRadius: "50%",
              background: tg.link,
              color: "#fff",
              fontSize: 26,
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              transform: `scale(${t})`,
            }}
          >
            {(order as number) + 1}
          </div>
        </>
      ) : (
        <div
          style={{
            position: "absolute",
            top: 10,
            right: 10,
            width: 44,
            height: 44,
            borderRadius: "50%",
            border: "3px solid rgba(255,255,255,0.85)",
            background: "rgba(0,0,0,0.15)",
          }}
        />
      )}
    </div>
  );
};


const CameraCell: React.FC<{ frame: number }> = ({ frame }) => {
  const tapped = frame >= CAMERA_TAP && frame < CAMERA_TAP + f(12);
  return (
    <div
      style={{
        position: "relative",
        aspectRatio: "1 / 1",
        borderRadius: 6,
        overflow: "hidden",
        background: "#0b0b0c",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 10,
        border: tapped ? `4px solid ${tg.link}` : "1px solid rgba(255,255,255,0.12)",
      }}
    >
      <div style={{ fontSize: 54, opacity: tapped ? 1 : 0.85 }}>📷</div>
      <div style={{ fontSize: 22, color: "rgba(255,255,255,0.7)" }}>Cámara</div>
    </div>
  );
};

export const AttachSheet: React.FC<{ startAt: number }> = ({ startAt }) => {
  const absolute = useCurrentFrame();
  const { fps } = useVideoConfig();
  const frame = absolute - startAt;

  const rise = spring({
    frame: frame - OPEN,
    fps,
    config: { damping: 200 },
    durationInFrames: f(20),
  });
  const fall = frame >= CLOSE ? Math.min(1, (frame - CLOSE) / f(12)) : 0;
  const y = interpolate(rise, [0, 1], [1, 0]) + fall;

  const count = PICK.filter((p) => frame >= p).length;
  const pressed = frame >= SEND && frame < SEND + f(10);
  const orderOf = (id: string) => {
    const i = PICKED.indexOf(id as (typeof PICKED)[number]);
    return i === -1 ? null : i;
  };

  return (
    <>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(0,0,0,0.45)",
          opacity: Math.max(0, rise - fall),
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          transform: `translateY(${y * 100}%)`,
          background: "#1c1c1e",
          borderTopLeftRadius: 26,
          borderTopRightRadius: 26,
          padding: "18px 16px 34px",
          fontFamily: tg.font,
        }}
      >
        <div
          style={{
            width: 92,
            height: 7,
            borderRadius: 999,
            background: "rgba(255,255,255,0.28)",
            margin: "0 auto 20px",
          }}
        />
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 8,
            marginBottom: 20,
            maxHeight: 730,
            overflow: "hidden",
          }}
        >
          <CameraCell frame={frame} />
          {GALLERY.map((p, i) => (
            <SheetPhoto key={p.id} index={i} order={orderOf(p.id)} frame={frame} />
          ))}
        </div>
        <div
          style={{
            background: pressed ? "rgba(106,179,243,0.35)" : "rgba(255,255,255,0.1)",
            borderRadius: 16,
            padding: "26px 0",
            textAlign: "center",
            fontSize: 34,
            fontWeight: 600,
            color: count > 0 ? tg.link : "rgba(255,255,255,0.35)",
            marginBottom: 10,
          }}
        >
          {count > 0 ? `Enviar ${count} ${count === 1 ? "elemento" : "elementos"}` : "Enviar"}
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-around",
            fontSize: 27,
            color: tg.textDim,
            paddingTop: 8,
          }}
        >
          <div>Galería</div>
          <div>Archivo</div>
          <div>Ubicación</div>
        </div>
      </div>
    </>
  );
};
