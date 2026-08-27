import React from "react";
import { AbsoluteFill, Audio, Series, staticFile } from "remotion";
import { TelegramChat } from "./telegram/Chat";
import { CHAT_DURATION, INTRO_DURATION, TOTAL_DURATION } from "./telegram/script";
import { tg } from "./telegram/theme";
import { Intro } from "./telegram/Intro";

export const FLUJO_DURATION = TOTAL_DURATION;

export const FlujoTelegram: React.FC = () => (
  <AbsoluteFill style={{ background: tg.chatBg }}>
    {/* La locución manda: los tiempos del guion se declaran contra este audio.
        VO-final.mp3 es el montaje de VO.mp3 con la cola de «VO fix.mp3», que
        pronuncia bien «ECU 911». Se rehace con scripts/vo-final.sh. */}
    <Audio src={staticFile("VO-final.mp3")} />
    <Series>
      <Series.Sequence durationInFrames={INTRO_DURATION}>
        <Intro />
      </Series.Sequence>
      <Series.Sequence durationInFrames={CHAT_DURATION}>
        <TelegramChat />
      </Series.Sequence>
    </Series>
  </AbsoluteFill>
);
