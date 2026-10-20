import React from "react";
import { Audio } from "@remotion/media";
import { AbsoluteFill, getStaticFiles, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import "./fonts";
import { SCENES } from "./beats";
import { Finish } from "./components/Finish";
import { Phone } from "./components/Phone";
import { CapturesProvider } from "./components/PhoneScreen";
import { FloorShadow, Stage } from "./components/Stage";
import { Scene } from "./lib/time";
import { lightAt, phoneBottom, poseAt } from "./phone-track";
import { ScreenRouter } from "./screens";
import { SCENE_PARTS } from "./scenes";

const PhoneLayer: React.FC<{ t: number }> = ({ t }) => {
  const pose = poseAt(t);
  const light = lightAt(t);
  if (pose.a <= 0.001) return null;
  const white = light.white > 0.5;
  return (
    <AbsoluteFill style={{ opacity: pose.a }}>
      <FloorShadow cx={pose.x} cy={phoneBottom(pose) + 8} unit={300 * pose.s} ring={light.ring} white={white} pitch={0.3} />
      <Phone pose={pose} light={light}>
        <ScreenRouter t={t} />
      </Phone>
    </AbsoluteFill>
  );
};

const audioSrc = () => {
  const files = getStaticFiles().map((f) => f.name);
  if (files.includes("audio/mix.wav")) return "audio/mix.wav";
  if (files.includes("audio/voice.wav")) return "audio/voice.wav";
  return null;
};

export const Film: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const pose = poseAt(t);
  const light = lightAt(t);
  const audio = audioSrc();
  return (
    <CapturesProvider>
      <AbsoluteFill style={{ background: "#030304" }}>
        {/* the keynote stage follows the phone */}
        <Stage light={{ cx: pose.x, cy: phoneBottom(pose) + 10, unit: 300 * pose.s, key: light.stageKey, white: light.white }} t={t} />
        {Object.entries(SCENE_PARTS).map(([id, part]) =>
          part.Back ? (
            <Scene key={`b-${id}`} name={`${id} (back)`} start={SCENES[id as keyof typeof SCENES].start} end={SCENES[id as keyof typeof SCENES].end}>
              <part.Back />
            </Scene>
          ) : null,
        )}
        <PhoneLayer t={t} />
        {Object.entries(SCENE_PARTS).map(([id, part]) =>
          part.Front ? (
            <Scene key={`f-${id}`} name={id} start={SCENES[id as keyof typeof SCENES].start} end={SCENES[id as keyof typeof SCENES].end}>
              <part.Front />
            </Scene>
          ) : null,
        )}
        <Finish t={t} white={light.white} />
        {audio ? <Audio src={staticFile(audio)} /> : null}
      </AbsoluteFill>
    </CapturesProvider>
  );
};
