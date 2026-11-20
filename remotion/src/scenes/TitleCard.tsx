import React from "react";
import { Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Scene } from "../schemas/render-props";

export interface TitleCardProps {
  scene: Scene;
}

export const TitleCard: React.FC<TitleCardProps> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const src = scene.visual.imageSrc || scene.visual.backgroundSrc;
  const resolvedSrc = src ? staticFile(src) : null;

  // Hiệu ứng fade in và spring scale cho tiêu đề
  const opacity = interpolate(frame, [0, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const popScale = spring({
    frame,
    fps,
    config: { damping: 15, stiffness: 100, mass: 0.8 },
  });

  return (
    <div className="relative w-full h-full overflow-hidden bg-black flex items-center justify-center">
      {/* Nền làm tối tĩnh với lớp vignette sạch (không dùng blur chạy từng frame) */}
      {resolvedSrc && (
        <div className="absolute inset-0 pointer-events-none scale-105">
          <Img
            src={resolvedSrc}
            className="w-full h-full object-cover opacity-30 grayscale-[40%]"
            alt="title background"
          />
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background:
                "radial-gradient(circle at center, rgba(0,0,0,0.15) 0%, rgba(0,0,0,0.72) 100%)",
            }}
          />
        </div>
      )}

      {/* Khung chữ Tiêu đề chương */}
      <div
        className="relative z-10 flex flex-col items-center text-center px-12 will-change-transform"
        style={{
          opacity,
          transform: `scale(${popScale})`,
          fontFamily: "var(--font-cinema), sans-serif",
        }}
      >
        <span className="text-amber-400/90 text-xl font-bold uppercase tracking-[0.35em] mb-4 [text-shadow:0_2px_6px_rgba(0,0,0,0.65)]">
          CineStory Remotion
        </span>

        <h1 className="text-white text-6xl md:text-7xl font-bold tracking-wide [text-shadow:0_8px_24px_rgba(0,0,0,0.85)] max-w-4xl leading-tight">
          {scene.rawText}
        </h1>

        <div className="w-24 h-1 bg-gradient-to-r from-transparent via-amber-400 to-transparent mt-6 rounded-full" />
      </div>
    </div>
  );
};
