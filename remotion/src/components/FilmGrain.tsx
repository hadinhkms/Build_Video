import React from "react";
import { random, staticFile, useCurrentFrame } from "remotion";

export interface FilmGrainProps {
  enabled: boolean;
  opacity?: number;
}

export const FilmGrain: React.FC<FilmGrainProps> = ({
  enabled,
  opacity = 0.075,
}) => {
  const frame = useCurrentFrame();

  if (!enabled) return null;

  // Dịch chuyển vị trí texture tất định theo từng frame
  const shiftX = Math.round(random(`grain-x-${frame}`) * 256);
  const shiftY = Math.round(random(`grain-y-${frame}`) * 256);

  const textureUrl = staticFile("textures/grain_512.png");

  return (
    <div
      className="absolute inset-0 w-full h-full pointer-events-none overflow-hidden"
      style={{
        contain: "paint",
        overflow: "hidden",
        opacity,
        mixBlendMode: "overlay",
      }}
    >
      <div
        className="absolute top-0 left-0 pointer-events-none"
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "calc(100% + 256px)",
          height: "calc(100% + 256px)",
          backgroundImage: `url(${textureUrl})`,
          backgroundRepeat: "repeat",
          transform: `translate3d(-${shiftX}px, -${shiftY}px, 0)`,
          willChange: "transform",
        }}
      />
    </div>
  );
};
