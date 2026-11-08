import React from "react";
import { SceneAudioPlayer } from "../components/AudioLayer";
import { AtmosphericEffects } from "../components/AtmosphericEffects";
import { BackgroundPlate } from "../components/BackgroundPlate";
import { CharacterLayer } from "../components/CharacterLayer";
import { SubtitleBox } from "../components/SubtitleBox";
import { Scene, Style } from "../schemas/render-props";

export interface CinematicStorySceneProps {
  scene: Scene;
  style: Style;
}

export const CinematicStoryScene: React.FC<CinematicStorySceneProps> = ({
  scene,
  style,
}) => {
  const { visual, cameraMotion, durationInFrames, grade, effects, captions } = scene;

  // Tính khoảng cách thanh phụ đề cách đáy dựa trên letterbox
  const bottomOffsetPx = style.letterboxRatio ? 170 : 130;

  return (
    <div className="relative w-full h-full overflow-hidden bg-black">
      {/* 1. Lớp Plate bối cảnh (Background) */}
      <BackgroundPlate
        backgroundSrc={visual.backgroundSrc}
        imageSrc={visual.imageSrc}
        cropRect={visual.cropRect}
        cameraMotion={cameraMotion}
        durationInFrames={durationInFrames}
        grade={grade}
      />

      {/* 2. Lớp Nhân vật 2.5D (Character) với Parallax depth = 1.35 */}
      <CharacterLayer
        characterSrc={visual.characterSrc}
        characterAnchor={visual.characterAnchor}
        cropRect={visual.cropRect}
        cameraMotion={cameraMotion}
        durationInFrames={durationInFrames}
        grade={grade}
        faceRig={visual.faceRig}
        mouthEnvelope={scene.mouthEnvelope}
        act={scene.act}
        sceneId={scene.id}
      />

      {/* 3. Lớp Hiệu ứng Khí quyển (Atmospheric Effects: Mưa, Đèn lập lòe) */}
      <AtmosphericEffects
        effects={effects}
        durationInFrames={durationInFrames}
      />

      {/* 4. Phụ đề Điện ảnh (SubtitleBox) */}
      <SubtitleBox
        captions={captions}
        enabled={style.subtitles}
        bottomOffsetPx={bottomOffsetPx}
      />

      {/* 5. Giọng đọc và SFX trong cảnh */}
      <SceneAudioPlayer scene={scene} />
    </div>
  );
};
