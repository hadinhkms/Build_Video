import React from "react";
import { Img, staticFile, useCurrentFrame } from "remotion";
import { CameraMotion, cameraTransform } from "../lib/camera";
import { Grade, Rect } from "../schemas/render-props";

export interface BackgroundPlateProps {
  backgroundSrc: string | null;
  imageSrc: string | null;
  cropRect: Rect | null;
  cameraMotion: CameraMotion;
  durationInFrames: number;
  grade: Grade | null;
}

export const BackgroundPlate: React.FC<BackgroundPlateProps> = ({
  backgroundSrc,
  imageSrc,
  cropRect,
  cameraMotion,
  durationInFrames,
  grade,
}) => {
  const frame = useCurrentFrame();
  const { scale, xPercent } = cameraTransform(
    cameraMotion,
    frame,
    durationInFrames,
    1.0
  );

  const src = backgroundSrc || imageSrc;
  if (!src) return null;

  const resolvedSrc = staticFile(src);
  const rawFilter = grade?.cssFilter?.trim();
  const cssFilter =
    rawFilter && rawFilter.toLowerCase() !== "none" ? rawFilter : undefined;

  // 1. Chế độ Layered (có cropRect) — đặt filter trên wrapper 1920x1080 đã clip để giảm ~11× VRAM
  if (cropRect && backgroundSrc) {
    const { x, y, w, h } = cropRect;
    const innerWidthPercent = 100 / Math.max(0.01, w);
    const innerHeightPercent = 100 / Math.max(0.01, h);
    const innerLeftPercent = -x * innerWidthPercent;
    const innerTopPercent = -y * innerHeightPercent;

    return (
      <div
        className="absolute inset-0 overflow-hidden w-full h-full pointer-events-none"
        style={{
          contain: "layout style",
          filter: cssFilter,
        }}
      >
        <div
          className="absolute inset-0 w-full h-full will-change-transform"
          style={{
            transform: `scale(${scale}) translate3d(${xPercent}%, 0, 0)`,
            transformOrigin: "center center",
          }}
        >
          <div
            className="absolute"
            style={{
              width: `${innerWidthPercent}%`,
              height: `${innerHeightPercent}%`,
              left: `${innerLeftPercent}%`,
              top: `${innerTopPercent}%`,
            }}
          >
            <Img
              src={resolvedSrc}
              className="w-full h-full object-cover"
              alt="background plate"
            />
            {grade?.overlayGradient && (
              <div
                className="absolute inset-0 pointer-events-none"
                style={{
                  background: grade.overlayGradient,
                  mixBlendMode: grade.overlayBlend as any,
                }}
              />
            )}
          </div>
        </div>
      </div>
    );
  }

  // 2. Chế độ Full Image (ảnh tĩnh đơn lớp)
  return (
    <div
      className="absolute inset-0 overflow-hidden w-full h-full pointer-events-none"
      style={{
        contain: "layout style",
        filter: cssFilter,
      }}
    >
      <div
        className="absolute inset-0 w-full h-full will-change-transform"
        style={{
          transform: `scale(${scale}) translate3d(${xPercent}%, 0, 0)`,
          transformOrigin: "center center",
        }}
      >
        <Img
          src={resolvedSrc}
          className="w-full h-full object-cover"
          alt="full scene image"
        />
        {grade?.overlayGradient && (
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background: grade.overlayGradient,
              mixBlendMode: grade.overlayBlend as any,
            }}
          />
        )}
      </div>
    </div>
  );
};
