import React from "react";
import { AbsoluteFill, Series } from "remotion";
import { AudioLayer } from "../components/AudioLayer";
import { CinematicLetterbox } from "../components/CinematicLetterbox";
import { FilmGrain } from "../components/FilmGrain";
import { RenderProps } from "../schemas/render-props";
import { HybridVideoSlot } from "../components/HybridVideoSlot";
import { EndScreen } from "./EndScreen";
import { TitleCard } from "./TitleCard";

export const StoryComposition: React.FC<RenderProps> = ({
  scenes,
  ambience,
  bgm,
  style,
}) => {
  return (
    <AbsoluteFill className="bg-black select-none overflow-hidden">
      {/* 1. Chuỗi phân cảnh (Story Scenes Series) */}
      <Series>
        {scenes.map((scene) => {
          return (
            <Series.Sequence
              key={scene.id}
              durationInFrames={scene.durationInFrames}
            >
              {scene.kind === "title_card" ? (
                <TitleCard scene={scene} />
              ) : scene.kind === "end_screen" ? (
                <EndScreen scene={scene} />
              ) : (
                <HybridVideoSlot scene={scene} style={style} />
              )}
            </Series.Sequence>
          );
        })}
      </Series>

      {/* 2. Lớp Âm thanh toàn cục (Ambience môi trường & BGM ducking) */}
      <AudioLayer ambience={ambience} bgm={bgm} />

      {/* 3. Lớp Film Grain điện ảnh (tất định) */}
      <FilmGrain enabled={style.grain} />

      {/* 4. Khung đen Cinematic Letterbox */}
      <CinematicLetterbox letterboxRatio={style.letterboxRatio} />
    </AbsoluteFill>
  );
};
