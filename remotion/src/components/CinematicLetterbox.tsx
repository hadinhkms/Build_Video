import React from "react";
import { useVideoConfig } from "remotion";

export interface CinematicLetterboxProps {
  letterboxRatio: number | null;
}

export const CinematicLetterbox: React.FC<CinematicLetterboxProps> = ({
  letterboxRatio,
}) => {
  const { width, height } = useVideoConfig();

  if (!letterboxRatio || letterboxRatio <= 0) return null;

  // Ví dụ 1920 / 2.39 ≈ 803px -> barHeight = (1080 - 803) / 2 ≈ 138.5px
  const visibleHeight = width / letterboxRatio;
  const barHeight = Math.max(0, (height - visibleHeight) / 2);

  if (barHeight < 1) return null;

  return (
    <div className="absolute inset-0 w-full h-full pointer-events-none z-40">
      {/* Thanh đen trên */}
      <div
        className="absolute top-0 left-0 right-0 bg-black pointer-events-none"
        style={{ height: `${barHeight}px` }}
      />
      {/* Thanh đen dưới */}
      <div
        className="absolute bottom-0 left-0 right-0 bg-black pointer-events-none"
        style={{ height: `${barHeight}px` }}
      />
    </div>
  );
};
