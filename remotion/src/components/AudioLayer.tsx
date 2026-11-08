import React from "react";
import { Html5Audio, Sequence, staticFile, useVideoConfig } from "remotion";
import { calculateBgmVolume } from "../lib/ducking";
import { Ambience, Bgm, Scene } from "../schemas/render-props";

export interface AudioLayerProps {
  ambience: Ambience[];
  bgm: Bgm | null;
}

export const AudioLayer: React.FC<AudioLayerProps> = ({ ambience, bgm }) => {
  const { fps } = useVideoConfig();

  return (
    <>
      {/* 1. Lớp BGM nền (có ducking theo thoại và cắt ở Cliffhanger) */}
      {bgm && (
        <Html5Audio
          loop
          src={staticFile(bgm.src)}
          volume={(f) =>
            calculateBgmVolume(f / fps, {
              volume: bgm.volume,
              duckedVolume: bgm.duckedVolume,
              duckIntervals: bgm.duckIntervals,
              cutAtSec: bgm.cutAtSec,
            })
          }
        />
      )}

      {/* 2. Lớp Ambience (môi trường theo thời gian tuyệt đối) */}
      {ambience.map((amb, index) => {
        const fromFrame = Math.round(amb.startSec * fps);
        const durationFrames = Math.max(
          1,
          Math.round((amb.endSec - amb.startSec) * fps)
        );

        return (
          <Sequence
            key={`amb-${index}`}
            from={fromFrame}
            durationInFrames={durationFrames}
          >
            <Html5Audio loop src={staticFile(amb.src)} volume={amb.volume} />
          </Sequence>
        );
      })}
    </>
  );
};

export interface SceneAudioPlayerProps {
  scene: Scene;
}

/**
 * Phát giọng đọc (voice) và âm thanh hiệu ứng (sfx) bên trong Sequence của từng cảnh.
 */
export const SceneAudioPlayer: React.FC<SceneAudioPlayerProps> = ({ scene }) => {
  const { fps } = useVideoConfig();

  return (
    <>
      {/* Giọng đọc Voice */}
      {scene.audio && (
        <Html5Audio
          src={staticFile(scene.audio.src)}
          trimBefore={Math.round(scene.audio.startInFileSec * fps)}
        />
      )}

      {/* SFX one-shot trong cảnh */}
      {scene.sfx.map((s, idx) => {
        const fromFrame = Math.max(0, Math.round(s.startSec * fps));
        const durationFrames = s.durationSec
          ? Math.max(1, Math.round(s.durationSec * fps))
          : undefined;

        return (
          <Sequence
            key={`sfx-${scene.id}-${idx}`}
            from={fromFrame}
            durationInFrames={durationFrames}
          >
            <Html5Audio src={staticFile(s.src)} volume={s.volume} />
          </Sequence>
        );
      })}
    </>
  );
};
