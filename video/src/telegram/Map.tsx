import React from "react";
import { Img, staticFile } from "remotion";

/**
 * Mapa real de Puerto Ayora (Santa Cruz, Galápagos) compuesto con nueve tiles
 * de OpenStreetMap descargados a public/mapa. Zoom 15, centro -0.7437, -90.3139.
 */
const Z = 15;
const CX = 8163;
const CY = 16451;
const FX = 0.4281; // posición fraccional del centro dentro del tile central
const FY = 0.6951;
const TILE = 256;
const SCALE = 1.9;

export const LocationMap: React.FC<{ width: number; height: number }> = ({ width, height }) => {
  const mosaic = TILE * 3 * SCALE;
  // Centro geográfico en píxeles dentro del mosaico ya escalado
  const centerX = (TILE + FX * TILE) * SCALE;
  const centerY = (TILE + FY * TILE) * SCALE;

  return (
    <div style={{ position: "relative", width, height, overflow: "hidden", background: "#aad3df" }}>
      <div
        style={{
          position: "absolute",
          left: width / 2 - centerX,
          top: height / 2 - centerY,
          width: mosaic,
          height: mosaic,
          display: "grid",
          gridTemplateColumns: `repeat(3, ${TILE * SCALE}px)`,
          gridTemplateRows: `repeat(3, ${TILE * SCALE}px)`,
        }}
      >
        {[-1, 0, 1].map((dy) =>
          [-1, 0, 1].map((dx) => (
            <Img
              key={`${dx}:${dy}`}
              src={staticFile(`mapa/t_${CX + dx}_${CY + dy}.png`)}
              style={{ width: TILE * SCALE, height: TILE * SCALE, display: "block" }}
            />
          )),
        )}
      </div>

      {/* Pin de Telegram sobre el punto compartido */}
      <div
        style={{
          position: "absolute",
          left: width / 2,
          top: height / 2,
          transform: "translate(-50%, -100%)",
          fontSize: 0,
        }}
      >
        <div
          style={{
            width: 62,
            height: 62,
            borderRadius: "50%",
            background: "#ef5350",
            border: "5px solid #fff",
            boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 32,
          }}
        >
          📍
        </div>
        <div
          style={{
            width: 14,
            height: 14,
            borderRadius: "50%",
            background: "rgba(0,0,0,0.35)",
            margin: "6px auto 0",
          }}
        />
      </div>

      <div
        style={{
          position: "absolute",
          left: 10,
          bottom: 8,
          fontSize: 18,
          color: "#33404d",
          background: "rgba(255,255,255,0.7)",
          borderRadius: 4,
          padding: "2px 8px",
        }}
      >
        © OpenStreetMap · z{Z}
      </div>
    </div>
  );
};
