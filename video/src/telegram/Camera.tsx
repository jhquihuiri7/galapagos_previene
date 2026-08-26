import React from "react";
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { tg } from "./theme";
import { byId } from "./photos";
import { HomeIndicator } from "./Frame";

/**
 * Cámara a pantalla completa y previsualización de la foto tomada, siguiendo el
 * recorrido del video de referencia: visor con obturador, disparo, y pantalla de
 * confirmación con contador y botón de enviar.
 */

// Fases relativas a la apertura de la cámara
const SHUTTER = 36; // se pulsa el obturador
const FLASH = 6; // duración del destello
const PREVIEW = 48; // aparece la previsualización
export const CAMERA_DURATION = 108; // al terminar, vuelve a la hoja

/** La foto que se toma es la columna de humo. */
const SHOT = "fuego-columna";

export const CameraScreen: React.FC<{ startAt: number }> = ({ startAt }) => {
  const absolute = useCurrentFrame();
  const { fps } = useVideoConfig();
  const frame = absolute - startAt;
  const photo = byId(SHOT);

  const open = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 12 });
  const closing = interpolate(frame, [CAMERA_DURATION - 10, CAMERA_DURATION], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const preview = frame >= PREVIEW;
  const flash =
    frame >= SHUTTER
      ? interpolate(frame, [SHUTTER, SHUTTER + FLASH], [1, 0], { extrapolateRight: "clamp" })
      : 0;
  const pressed = frame >= SHUTTER - 4 && frame < SHUTTER + 8;

  // Deriva leve del visor, como una mano sosteniendo el teléfono
  const drift = preview ? 0 : interpolate(frame, [0, SHUTTER], [0, 10], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill
      style={{
        opacity: Math.max(0, open - closing),
        background: "#000",
        fontFamily: tg.font,
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Visor / foto congelada */}
      <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
        <Img
          src={staticFile(photo.src)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: preview ? "none" : `scale(1.12) translate(${drift}px, ${-drift / 2}px)`,
          }}
        />
      </div>

      {flash > 0 ? (
        <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: flash }} />
      ) : null}

      {preview ? (
        <>
          {/* Cabecera de la previsualización: contador y confirmación */}
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              height: 200,
              background: "linear-gradient(180deg, rgba(0,0,0,0.6), transparent)",
              display: "flex",
              alignItems: "center",
              gap: 24,
              padding: "60px 34px 0",
            }}
          >
            <span style={{ fontSize: 46, color: "#fff" }}>‹</span>
            <div style={{ flex: 1, fontSize: 34, fontWeight: 600, color: "#fff" }}>
              Galápagos Previene
            </div>
            <div
              style={{
                width: 62,
                height: 62,
                borderRadius: "50%",
                border: "3px solid rgba(255,255,255,0.9)",
                color: "#fff",
                fontSize: 30,
                fontWeight: 700,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              1
            </div>
            <div
              style={{
                width: 66,
                height: 66,
                borderRadius: "50%",
                background: tg.link,
                color: "#fff",
                fontSize: 34,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              ✓
            </div>
          </div>

          {/* Pie: descripción opcional y envío */}
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              bottom: 34,
              padding: "0 26px 22px",
              display: "flex",
              flexDirection: "column",
              gap: 18,
            }}
          >
            <div
              style={{
                background: "rgba(0,0,0,0.55)",
                borderRadius: 999,
                height: 82,
                display: "flex",
                alignItems: "center",
                gap: 18,
                padding: "0 26px",
              }}
            >
              <span style={{ fontSize: 34 }}>📷</span>
              <span style={{ fontSize: 30, color: "rgba(255,255,255,0.65)" }}>
                Escribe una descripción…
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
              <div
                style={{
                  flex: 1,
                  background: "rgba(0,0,0,0.55)",
                  borderRadius: 999,
                  height: 82,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-around",
                  fontSize: 32,
                  color: "#fff",
                }}
              >
                <span>⤢</span>
                <span>🖌</span>
                <span>SD</span>
                <span>⚙</span>
              </div>
              <div
                style={{
                  width: 92,
                  height: 92,
                  borderRadius: "50%",
                  background: tg.link,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 40,
                }}
              >
                ➤
              </div>
            </div>
          </div>
        </>
      ) : (
        <>
          {/* Controles del visor */}
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              bottom: 34,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 22,
              paddingBottom: 30,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                width: "100%",
                padding: "0 70px",
              }}
            >
              <span style={{ fontSize: 40, color: "#fff", opacity: 0.9 }}>⚡</span>
              <div
                style={{
                  width: 132,
                  height: 132,
                  borderRadius: "50%",
                  border: "7px solid #fff",
                  background: pressed ? "rgba(255,255,255,0.35)" : "transparent",
                  transform: `scale(${pressed ? 0.92 : 1})`,
                }}
              />
              <span style={{ fontSize: 44, color: "#fff", opacity: 0.9 }}>⟳</span>
            </div>
            <div style={{ fontSize: 28, color: "#fff", textShadow: "0 2px 8px rgba(0,0,0,0.6)" }}>
              Toca para foto, mantén para video
            </div>
          </div>
        </>
      )}
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0 }}>
        <HomeIndicator />
      </div>
    </AbsoluteFill>
  );
};
