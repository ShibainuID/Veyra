import React from "react";
import { Composition } from "remotion";
import { DURATION_FRAMES, FPS, HEIGHT, WIDTH } from "./beats";
import { Film } from "./Film";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition id="VeyraLaunch" component={Film} durationInFrames={DURATION_FRAMES} fps={FPS} width={WIDTH} height={HEIGHT} />
    </>
  );
};
