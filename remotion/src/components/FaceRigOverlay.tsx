import React from "react";
import { Img, staticFile } from "remotion";
import { FaceRig } from "../schemas/render-props";

export interface FaceRigOverlayProps {
  faceRig?: FaceRig | null;
  blink: number;
  mouthOpen: number;
}

export const FaceRigOverlay: React.FC<FaceRigOverlayProps> = ({
  faceRig,
  blink,
  mouthOpen,
}) => {
  if (!faceRig) return null;

  return (
    <>
      {/* Patch mắt nhắm (chớp mắt ngẫu nhiên) */}
      {faceRig.eyesPatchSrc && faceRig.eyes && blink > 0.01 && (
        <div
          className="absolute pointer-events-none"
          style={{
            left: `${faceRig.eyes.x * 100}%`,
            top: `${faceRig.eyes.y * 100}%`,
            width: `${faceRig.eyes.w * 100}%`,
            height: `${faceRig.eyes.h * 100}%`,
            opacity: blink,
          }}
        >
          <Img
            src={staticFile(faceRig.eyesPatchSrc)}
            className="w-full h-full object-fill block"
            alt="eyes closed patch"
          />
        </div>
      )}

      {/* Patch miệng hé theo biên độ thoại */}
      {faceRig.mouthPatchSrc && faceRig.mouth && mouthOpen > 0.02 && (
        <div
          className="absolute pointer-events-none"
          style={{
            left: `${faceRig.mouth.x * 100}%`,
            top: `${faceRig.mouth.y * 100}%`,
            width: `${faceRig.mouth.w * 100}%`,
            height: `${faceRig.mouth.h * 100}%`,
            opacity: Math.min(0.85, mouthOpen),
            transform: `translateY(${mouthOpen * 2}px)`,
          }}
        >
          <Img
            src={staticFile(faceRig.mouthPatchSrc)}
            className="w-full h-full object-fill block"
            alt="mouth open patch"
          />
        </div>
      )}
    </>
  );
};
