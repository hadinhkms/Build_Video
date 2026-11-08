import React from "react";
import { Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { CameraMotion, cameraTransform } from "../lib/camera";
import { breathScale, blinkAmount, headDrift } from "../lib/life";
import { CharacterAnchor, FaceRig, Grade, Rect } from "../schemas/render-props";
import { FaceRigOverlay } from "./FaceRigOverlay";

export interface CharacterLayerProps {
  characterSrc: string | null;
  characterAnchor: CharacterAnchor | null;
  cropRect: Rect | null;
  cameraMotion: CameraMotion;
  durationInFrames: number;
  grade: Grade | null;
  faceRig?: FaceRig | null;
  mouthEnvelope?: number[] | null;
  act?: string;
  sceneId?: string;
}

export const CharacterLayer: React.FC<CharacterLayerProps> = ({
  characterSrc,
  characterAnchor,
  cropRect,
  cameraMotion,
  durationInFrames,
  grade,
  faceRig,
  mouthEnvelope,
  act = "SETUP",
  sceneId = "default",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (!characterSrc || !characterAnchor) return null;

  const t = frame / fps;
  const seed = `${characterSrc}-${sceneId}`;

  // 1. Chuyển động Camera Parallax (depth = 1.35)
  const { scale, xPercent } = cameraTransform(cameraMotion, frame, durationInFrames, 1.35);

  // 2. Tín hiệu sống nhân vật (Life system)
  const bScale = breathScale(t, act);
  const drift = headDrift(t, seed);
  const blink = blinkAmount(t, seed);

  // Khẩu hình miệng theo biên độ âm thanh
  const mouthOpen = mouthEnvelope && frame < mouthEnvelope.length ? mouthEnvelope[frame] : 0;
  const speechNodDeg = !faceRig?.mouthPatchSrc && mouthOpen > 0.05 ? mouthOpen * 0.3 : 0;

  // 3. Tính tọa độ nhân vật trong khung nhìn
  let centerPercent = characterAnchor.x * 100;
  let bottomPercent = characterAnchor.y * 100;
  let heightPercent = characterAnchor.height * 100;

  if (cropRect) {
    const { x: cx, y: cy, w: cw, h: ch } = cropRect;
    centerPercent = ((characterAnchor.x - cx) / Math.max(0.01, cw)) * 100;
    bottomPercent = ((characterAnchor.y - cy) / Math.max(0.01, ch)) * 100;
    heightPercent = (characterAnchor.height / Math.max(0.01, ch)) * 100;
  }

  const shadowOpacity = grade?.contactShadowOpacity ?? 0.45;

  return (
    <div className="absolute inset-0 overflow-hidden w-full h-full pointer-events-none">
      <div
        className="absolute inset-0 w-full h-full will-change-transform"
        style={{
          transform: `scale(${scale}) translate3d(${xPercent}%, 0, 0)`,
          transformOrigin: "center center",
        }}
      >
        {/* Bóng đổ tiếp xúc dưới chân (Contact Shadow) */}
        <div
          className="absolute pointer-events-none"
          style={{
            left: `${centerPercent}%`,
            top: `${bottomPercent}%`,
            transform: "translate(-50%, -50%)",
            width: `${heightPercent * 0.55}%`,
            height: "24px",
            background: "radial-gradient(ellipse at center, rgba(0, 0, 0, 0.85) 0%, rgba(0, 0, 0, 0) 75%)",
            opacity: shadowOpacity,
          }}
        />

        {/* Lớp nhân vật đã tách nền với nhịp thở và micro drift */}
        <div
          className="absolute pointer-events-none"
          style={{
            left: `${centerPercent}%`,
            top: `${bottomPercent}%`,
            height: `${heightPercent}%`,
            transform: `translate(-50%, -100%) scaleY(${bScale}) translate3d(${drift.translateX}px, ${drift.translateY}px, 0) rotate(${drift.rotateDeg + speechNodDeg}deg)`,
            transformOrigin: "bottom center",
            filter: grade?.cssFilter ?? undefined,
          }}
        >
          <Img
            src={staticFile(characterSrc)}
            className="h-full w-auto object-contain block select-none pointer-events-none"
            alt="character cutout"
          />

          <FaceRigOverlay faceRig={faceRig} blink={blink} mouthOpen={mouthOpen} />
        </div>
      </div>
    </div>
  );
};
