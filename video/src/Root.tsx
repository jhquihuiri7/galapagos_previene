import React from "react";
import { Composition } from "remotion";
import { FlujoTelegram, FLUJO_DURATION } from "./Composition";
import { FPS } from "./telegram/timing";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="FlujoTelegram"
      component={FlujoTelegram}
      durationInFrames={FLUJO_DURATION}
      fps={FPS}
      width={1080}
      height={1920}
    />
  );
};
