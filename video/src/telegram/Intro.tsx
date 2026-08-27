import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { tg } from "./theme";
import { CHAT_BACKGROUND, Header, HomeIndicator, StatusBar } from "./Frame";
import { INTRO_DURATION } from "./script";
import { f } from "./timing";

/** Pantalla de un bot recién abierto: chat vacío y el botón ancho INICIAR. */
export const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: frame - f(8), fps, config: { damping: 200 }, durationInFrames: f(18) });
  // La pulsación de INICIAR cierra la intro: siempre pegada a su final.
  const press = interpolate(frame, [INTRO_DURATION - f(22), INTRO_DURATION - f(8)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: CHAT_BACKGROUND,
        fontFamily: tg.font,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <StatusBar />
      <Header typing={false} />
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 26,
          opacity: enter,
          transform: `translateY(${interpolate(enter, [0, 1], [20, 0])}px)`,
          padding: "0 70px",
        }}
      >
        <Img
          src={staticFile("icon.jpeg")}
          style={{
            width: 320,
            height: 320,
            borderRadius: "50%",
            objectFit: "cover",
            boxShadow: "0 18px 48px rgba(0,0,0,0.45)",
          }}
        />
        <div style={{ fontSize: 44, fontWeight: 600, color: tg.text, textAlign: "center" }}>
          Galápagos Previene
        </div>
        <div
          style={{
            background: tg.service,
            borderRadius: 999,
            padding: "12px 28px",
            fontSize: 27,
            color: tg.text,
            textAlign: "center",
          }}
        >
          Flujo de reporte, mensaje por mensaje
        </div>
        <div style={{ fontSize: 26, color: tg.textDim, textAlign: "center", lineHeight: 1.6 }}>
          Este bot solo atiende reportes.{"\n"}Para emergencias en curso, ECU 911.
        </div>
      </div>
      <div
        style={{
          background: tg.header,
          height: 130,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            fontSize: 34,
            fontWeight: 600,
            letterSpacing: 2,
            color: tg.link,
            opacity: interpolate(press, [0, 1], [1, 0.45]),
          }}
        >
          INICIAR
        </div>
      </div>
      <HomeIndicator />
    </AbsoluteFill>
  );
};
