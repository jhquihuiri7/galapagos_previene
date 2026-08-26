import React from "react";
import { Composition } from "remotion";
import { FlujoTelegram, FLUJO_DURATION } from "./Composition";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="FlujoTelegram"
      component={FlujoTelegram}
      durationInFrames={FLUJO_DURATION}
      fps={30}
      width={1080}
      height={1920}
    />
  );
};
