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
import { COMMAND_MENU, events, type Btn, type Event } from "./script";
import { CHAT_BACKGROUND, Composer, Header, HomeIndicator, StatusBar } from "./Frame";
import {
  AttachSheet,
  CAMERA_OPEN,
  SHEET_DURATION,
  SHEET_HEIGHT,
  sheetProgress,
} from "./AttachSheet";
import { CAMERA_DURATION, CameraScreen } from "./Camera";
import { byId } from "./photos";
import { LocationMap } from "./Map";
import { f } from "./timing";

type Bubble = {
  id: string;
  from: "user" | "bot";
  at: number;
  text: string;
  buttons?: Btn[][];
  album?: string[];
  location?: boolean;
  editedAt?: number;
};

type Item = { kind: "bubble"; data: Bubble } | { kind: "service"; id: string; at: number; text: string };

const buildState = (frame: number) => {
  const items: Item[] = [];
  const index = new Map<string, Bubble>();
  let keyboard: Btn[] | null = null;
  let commands = false;
  let tap: { id: string; label: Btn; at: number } | null = null;
  let sheetAt: number | null = null;

  for (const e of events as Event[]) {
    if (e.at > frame) continue;
    if (e.t === "msg") {
      const bubble: Bubble = {
        id: e.id,
        from: e.from,
        at: e.at,
        text: e.text,
        buttons: e.buttons,
        album: e.album,
        location: e.location,
      };
      index.set(e.id, bubble);
      items.push({ kind: "bubble", data: bubble });
    } else if (e.t === "edit") {
      const b = index.get(e.id);
      if (b) {
        b.text = e.text;
        b.buttons = e.buttons;
        b.editedAt = e.at;
      }
    } else if (e.t === "service") {
      items.push({ kind: "service", id: e.id, at: e.at, text: e.text });
    } else if (e.t === "keyboard") {
      keyboard = e.labels;
    } else if (e.t === "commands") {
      commands = e.show;
    } else if (e.t === "attach") {
      sheetAt = frame - e.at < SHEET_DURATION ? e.at : null;
    } else if (e.t === "tap") {
      if (frame - e.at < f(18)) tap = { id: e.id, label: e.label, at: e.at };
    }
  }
  return { items, keyboard, commands, tap, sheetAt };
};

const Time: React.FC<{ out?: boolean }> = ({ out }) => (
  <span
    style={{
      fontSize: 22,
      color: out ? tg.timeOut : tg.timeIn,
      marginLeft: 14,
      whiteSpace: "nowrap",
      verticalAlign: "bottom",
    }}
  >
    10:24{out ? " ✓✓" : ""}
  </span>
);

const InlineButtons: React.FC<{
  rows: Btn[][];
  tapped: Btn | null;
  tapProgress: number;
}> = ({ rows, tapped, tapProgress }) => (
  <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 4 }}>
    {rows.map((row, i) => (
      <div key={i} style={{ display: "flex", gap: 4 }}>
        {row.map((label) => {
          const isTapped = tapped === label;
          return (
            <div
              key={label}
              style={{
                flex: 1,
                textAlign: "center",
                background: isTapped
                  ? `rgba(106,179,243,${0.35 * (1 - tapProgress) + 0.12})`
                  : tg.inlineBtn,
                border: `1px solid ${tg.inlineBtnBorder}`,
                borderRadius: 10,
                padding: "16px 12px",
                fontSize: 27,
                lineHeight: 1.2,
                color: tg.text,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                minHeight: 66,
              }}
            >
              {label}
            </div>
          );
        })}
      </div>
    ))}
  </div>
);


/** Mosaico de Telegram para tres medios: una grande y dos apiladas al lado. */
const AlbumView: React.FC<{ ids: string[] }> = ({ ids }) => {
  const [first, ...rest] = ids;
  const cell = (id: string, style: React.CSSProperties) => {
    const photo = byId(id);
    return (
      <div key={id} style={{ position: "relative", overflow: "hidden", background: photo.bg, ...style }}>
        <Img
          src={staticFile(photo.src)}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
        />
      </div>
    );
  };
  return (
    <div style={{ width: 720, height: 560, display: "flex", gap: 4, position: "relative" }}>
      {cell(first, { flex: 2, borderTopLeftRadius: 14, borderBottomLeftRadius: 14 })}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
        {cell(rest[0], { flex: 1, borderTopRightRadius: 14 })}
        {cell(rest[1], { flex: 1, borderBottomRightRadius: 14 })}
      </div>
      <div
        style={{
          position: "absolute",
          right: 14,
          bottom: 12,
          background: "rgba(0,0,0,0.45)",
          borderRadius: 999,
          padding: "6px 16px",
          fontSize: 22,
          color: "#fff",
        }}
      >
        10:24 ✓✓
      </div>
    </div>
  );
};

/** Burbuja de ubicación de Telegram: mapa con pin y pie con el lugar. */
const LocationView: React.FC = () => (
  <div style={{ width: 700, borderRadius: 14, overflow: "hidden" }}>
    <LocationMap width={700} height={420} />
    <div style={{ background: tg.bubbleOut, padding: "16px 20px 14px" }}>
      <div style={{ fontSize: 30, color: tg.text }}>Ubicación</div>
      <div style={{ fontSize: 25, color: tg.timeOut, marginTop: 4 }}>
        Puerto Ayora, Santa Cruz · 10:24 ✓✓
      </div>
    </div>
  </div>
);

const BubbleView: React.FC<{ b: Bubble; tap: { id: string; label: Btn; at: number } | null }> = ({
  b,
  tap,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: frame - b.at, fps, config: { damping: 200 }, durationInFrames: f(14) });
  const out = b.from === "user";
  const editPulse = b.editedAt
    ? interpolate(frame - b.editedAt, [0, f(10)], [0.55, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" })
    : 1;
  const tapped = tap && tap.id === b.id ? tap.label : null;
  const tapProgress = tap ? Math.min(1, (frame - tap.at) / f(18)) : 0;

  return (
    <div
      style={{
        display: "flex",
        justifyContent: out ? "flex-end" : "flex-start",
        opacity: enter,
        transform: `translateY(${interpolate(enter, [0, 1], [18, 0])}px)`,
        padding: "0 22px",
      }}
    >
      <div
        style={{
          maxWidth: 800,
          minWidth: b.buttons ? 800 : 0,
          background: b.album || b.location ? "transparent" : out ? tg.bubbleOut : tg.bubbleIn,
          borderRadius: 16,
          borderBottomRightRadius: out ? 4 : 16,
          borderBottomLeftRadius: out ? 16 : 4,
          padding: b.album || b.location ? 0 : "18px 20px 14px",
          opacity: editPulse,
        }}
      >
        {b.album ? <AlbumView ids={b.album} /> : null}
        {b.location ? <LocationView /> : null}
        <div
          hidden={Boolean(b.album || b.location)}
          style={{
            fontSize: 32,
            lineHeight: 1.35,
            color: tg.text,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {b.text}
          <Time out={out} />
        </div>
        {b.buttons ? (
          <InlineButtons rows={b.buttons} tapped={tapped} tapProgress={tapProgress} />
        ) : null}
      </div>
    </div>
  );
};

const ServiceView: React.FC<{ text: string; at: number }> = ({ text, at }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: frame - at, fps, config: { damping: 200 }, durationInFrames: f(12) });
  return (
    <div style={{ display: "flex", justifyContent: "center", opacity: enter }}>
      <div
        style={{
          background: tg.service,
          color: tg.text,
          borderRadius: 999,
          padding: "10px 24px",
          fontSize: 25,
        }}
      >
        {text}
      </div>
    </div>
  );
};

const CommandMenu: React.FC = () => (
  <div style={{ padding: "0 22px 10px" }}>
    <div style={{ background: tg.header, borderRadius: 14, overflow: "hidden" }}>
      {COMMAND_MENU.map(([cmd, desc]) => (
        <div
          key={cmd}
          style={{
            display: "flex",
            gap: 18,
            alignItems: "baseline",
            padding: "20px 26px",
            borderBottom: `1px solid ${tg.headerLine}`,
          }}
        >
          <div style={{ fontSize: 30, color: tg.link, minWidth: 190 }}>{cmd}</div>
          <div style={{ fontSize: 28, color: tg.textDim }}>{desc}</div>
        </div>
      ))}
    </div>
  </div>
);

export const TelegramChat: React.FC = () => {
  const frame = useCurrentFrame();
  const { items, keyboard, commands, tap, sheetAt } = buildState(frame);

  // El header dice "escribiendo…" justo antes de cada mensaje del bot
  const typing = events.some(
    (e) => e.t === "msg" && e.from === "bot" && e.at - frame > 0 && e.at - frame < f(26),
  );
  const draft = commands ? "/" : "";

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
      <Header typing={typing} />
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-end",
          gap: 14,
          paddingBottom:
            18 + (sheetAt === null ? 0 : sheetProgress(frame - sheetAt) * SHEET_HEIGHT),
          overflow: "hidden",
        }}
      >
        {items.map((item) =>
          item.kind === "bubble" ? (
            <BubbleView key={item.data.id} b={item.data} tap={tap} />
          ) : (
            <ServiceView key={item.id} text={item.text} at={item.at} />
          ),
        )}
      </div>
      {commands ? <CommandMenu /> : null}
      <Composer keyboard={keyboard} draft={draft} clipActive={sheetAt !== null} />
      <HomeIndicator />
      {sheetAt !== null ? <AttachSheet startAt={sheetAt} /> : null}
      {sheetAt !== null &&
      frame - sheetAt >= CAMERA_OPEN &&
      frame - sheetAt < CAMERA_OPEN + CAMERA_DURATION ? (
        <CameraScreen startAt={sheetAt + CAMERA_OPEN} />
      ) : null}
    </AbsoluteFill>
  );
};
