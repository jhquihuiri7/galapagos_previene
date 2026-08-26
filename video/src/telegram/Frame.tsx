import React from "react";
import { Img, staticFile, useCurrentFrame } from "remotion";
import { tg } from "./theme";
import type { Btn } from "./script";

export const CHAT_BACKGROUND = `radial-gradient(120% 80% at 50% 0%, #16212e 0%, ${tg.chatBg} 60%)`;

/** Barra de estado de iOS con Dynamic Island. */
export const StatusBar: React.FC = () => (
  <div
    style={{
      height: 92,
      background: tg.header,
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      padding: "0 46px",
      color: tg.text,
      fontSize: 28,
      fontWeight: 600,
      flexShrink: 0,
      position: "relative",
    }}
  >
    <div style={{ minWidth: 120 }}>10:24</div>
    <div
      style={{
        position: "absolute",
        left: "50%",
        transform: "translateX(-50%)",
        top: 18,
        width: 240,
        height: 58,
        borderRadius: 999,
        background: "#000",
      }}
    />
    <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 120, justifyContent: "flex-end" }}>
      <span style={{ fontSize: 24 }}>▂▄▆</span>
      <span style={{ fontSize: 24 }}>WiFi</span>
      <span
        style={{
          width: 46,
          height: 24,
          borderRadius: 6,
          border: "2px solid rgba(255,255,255,0.6)",
          padding: 3,
          display: "inline-flex",
        }}
      >
        <span style={{ flex: 1, background: tg.text, borderRadius: 3 }} />
      </span>
    </div>
  </div>
);

/** Indicador de inicio de iPhone. */
export const HomeIndicator: React.FC = () => (
  <div
    style={{
      height: 34,
      background: tg.header,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      flexShrink: 0,
    }}
  >
    <div style={{ width: 260, height: 8, borderRadius: 999, background: "rgba(255,255,255,0.5)" }} />
  </div>
);

/** Cabecera de conversación de Telegram iOS: título centrado, avatar a la derecha. */
export const Header: React.FC<{ typing: boolean }> = ({ typing }) => (
  <div
    style={{
      background: tg.header,
      borderBottom: `1px solid ${tg.headerLine}`,
      padding: "0 28px",
      height: 124,
      display: "flex",
      alignItems: "center",
      gap: 18,
      flexShrink: 0,
    }}
  >
    <div style={{ display: "flex", alignItems: "center", color: tg.link, minWidth: 150 }}>
      <span style={{ fontSize: 46, lineHeight: 1, marginRight: 6 }}>‹</span>
      <span style={{ fontSize: 30 }}>Atrás</span>
    </div>
    <div style={{ flex: 1, textAlign: "center" }}>
      <div style={{ fontSize: 32, fontWeight: 600, color: tg.text }}>Galápagos Previene</div>
      <div style={{ fontSize: 25, color: typing ? tg.link : tg.textDim, marginTop: 3 }}>
        {typing ? "escribiendo…" : "bot"}
      </div>
    </div>
    <Img
      src={staticFile("icon.jpeg")}
      style={{
        width: 76,
        height: 76,
        minWidth: 76,
        borderRadius: "50%",
        objectFit: "cover",
      }}
    />
  </div>
);

/** Barra de composición de Telegram iOS: clip fuera, campo redondeado, emoji dentro. */
export const Composer: React.FC<{
  keyboard: Btn[] | null;
  draft: string;
  clipActive?: boolean;
}> = ({ keyboard, draft, clipActive }) => {
  const frame = useCurrentFrame();
  const caret = frame % 30 < 15 ? "|" : " ";
  return (
    <div style={{ flexShrink: 0, background: tg.header }}>
      {keyboard ? (
        <div style={{ padding: "12px 16px 4px", display: "flex", gap: 8 }}>
          {keyboard.map((label) => (
            <div
              key={label}
              style={{
                flex: 1,
                background: tg.replyBtn,
                borderRadius: 12,
                padding: "24px 20px",
                fontSize: 30,
                color: tg.text,
                textAlign: "center",
              }}
            >
              {label}
            </div>
          ))}
        </div>
      ) : null}
      <div
        style={{
          height: 124,
          display: "flex",
          alignItems: "center",
          gap: 22,
          padding: "0 28px",
        }}
      >
        <div
          style={{
            fontSize: 40,
            color: clipActive ? tg.link : tg.textDim,
            transform: clipActive ? "scale(1.12)" : "none",
          }}
        >
          📎
        </div>
        <div
          style={{
            flex: 1,
            background: "rgba(255,255,255,0.07)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 999,
            height: 74,
            display: "flex",
            alignItems: "center",
            padding: "0 26px",
            gap: 16,
          }}
        >
          <div style={{ flex: 1, fontSize: 31, color: draft ? tg.text : tg.textDim }}>
            {draft ? draft + caret : "Mensaje"}
          </div>
          <div style={{ fontSize: 32, color: tg.textDim }}>😊</div>
        </div>
        <div style={{ fontSize: 36, color: tg.textDim }}>🎤</div>
      </div>
    </div>
  );
};
