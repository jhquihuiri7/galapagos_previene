import React from "react";
import { AbsoluteFill, Series } from "remotion";
import { TelegramChat } from "./telegram/Chat";
import { CHAT_DURATION } from "./telegram/script";
import { tg } from "./telegram/theme";
import { Intro } from "./telegram/Intro";

export const FLUJO_DURATION = 100 + CHAT_DURATION;

export const FlujoTelegram: React.FC = () => (
  <AbsoluteFill style={{ background: tg.chatBg }}>
    <Series>
      <Series.Sequence durationInFrames={100}>
        <Intro />
      </Series.Sequence>
      <Series.Sequence durationInFrames={CHAT_DURATION}>
        <TelegramChat />
      </Series.Sequence>
    </Series>
  </AbsoluteFill>
);
