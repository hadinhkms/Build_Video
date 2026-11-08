import React from "react";
import { Freeze, Loop, OffthreadVideo, staticFile, useVideoConfig } from "remotion";
import { ClipFit, Scene, Style } from "../schemas/render-props";
import { AtmosphericEffects } from "./AtmosphericEffects";
import { SceneAudioPlayer } from "./AudioLayer";
import { SubtitleBox } from "./SubtitleBox";
import { CinematicStoryScene } from "../scenes/CinematicStoryScene";

export interface ClipWithFitProps {
  src: string;
  fit: ClipFit;
  clipDurationSec: number;
}

export const ClipWithFit: React.FC<ClipWithFitProps> = ({
  src,
  fit,
  clipDurationSec,
}) => {
  const { fps } = useVideoConfig();

  let videoElement = (
    <OffthreadVideo
      src={src}
      muted
      playbackRate={fit.playbackRate}
      className="w-full h-full object-cover block"
    />
  );

  if (fit.freezeAtFrame !== null) {
    videoElement = (
      <Freeze frame={fit.freezeAtFrame} active={(f) => f >= fit.freezeAtFrame!}>
        {videoElement}
      </Freeze>
    );
  } else if (fit.loop) {
    const loopDuration = Math.max(1, Math.floor(clipDurationSec * fps));
    videoElement = <Loop durationInFrames={loopDuration}>{videoElement}</Loop>;
  }

  return <div className="absolute inset-0 w-full h-full overflow-hidden bg-black">{videoElement}</div>;
};

export interface HybridVideoSlotProps {
  scene: Scene;
  style: Style;
}

export const HybridVideoSlot: React.FC<HybridVideoSlotProps> = ({ scene, style }) => {
  const { fps } = useVideoConfig();
  const { visual, grade, effects, captions, durationInFrames } = scene;

  // Nếu cảnh sử dụng clip AI (Kling / Hedra)
  if (visual.mode === "clip" && visual.clipSrc && visual.clipFit) {
    const bottomOffsetPx = style.letterboxRatio ? 170 : 130;
    const clipSec = visual.clipDurationSec ?? durationInFrames / fps;

    return (
      <div
        className="relative w-full h-full overflow-hidden bg-black"
        style={{
          filter: grade?.cssFilter ?? undefined,
        }}
      >
        {/* 1. Lớp Video Clip với playbackRate / Freeze / Loop */}
        <ClipWithFit
          src={staticFile(visual.clipSrc)}
          fit={visual.clipFit}
          clipDurationSec={clipSec}
        />

        {/* 2. Lớp Overlay Gradient theo Grade nếu có */}
        {grade?.overlayGradient && (
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background: grade.overlayGradient,
              mixBlendMode: grade.overlayBlend,
            }}
          />
        )}

        {/* 3. Lớp Hiệu ứng Khí quyển (Mưa, Flicker) */}
        <AtmosphericEffects effects={effects} durationInFrames={durationInFrames} />

        {/* 4. Lớp Phụ đề */}
        <SubtitleBox
          captions={captions}
          enabled={style.subtitles}
          bottomOffsetPx={bottomOffsetPx}
        />

        {/* 5. Giọng đọc và SFX */}
        <SceneAudioPlayer scene={scene} />
      </div>
    );
  }

  // Mặc định: Dựng 2.5D Raccord (Background Plate + Character Cutout + Parallax)
  return <CinematicStoryScene scene={scene} style={style} />;
};
