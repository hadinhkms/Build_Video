import React, { useEffect, useRef } from "react";
import { noise2D } from "@remotion/noise";
import { random, useCurrentFrame, useVideoConfig } from "remotion";
import { Effects } from "../schemas/render-props";

export interface AtmosphericEffectsProps {
  effects: Effects;
  durationInFrames: number;
}

export const AtmosphericEffects: React.FC<AtmosphericEffectsProps> = ({
  effects,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const { rain, rainRegion, flicker } = effects;

  // 1. Vẽ mưa tất định bằng canvas (random(seed) của Remotion)
  useEffect(() => {
    if (rain === "off") return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, width, height);

    // Xác định vùng mưa (toàn khung hoặc cửa sổ)
    let clipX = 0;
    let clipY = 0;
    let clipW = width;
    let clipH = height;

    if (rain === "window" && rainRegion) {
      clipX = rainRegion.x * width;
      clipY = rainRegion.y * height;
      clipW = rainRegion.w * width;
      clipH = rainRegion.h * height;
    }

    ctx.save();
    ctx.beginPath();
    ctx.rect(clipX, clipY, clipW, clipH);
    ctx.clip();

    const NUM_DROPS = 180;
    ctx.lineWidth = 1.2;
    ctx.strokeStyle = "rgba(220, 235, 255, 0.45)";

    for (let i = 0; i < NUM_DROPS; i++) {
      const dropSeed = `rain-drop-${i}`;
      const speed = 20 + random(`${dropSeed}-speed`) * 15;
      const length = 20 + random(`${dropSeed}-len`) * 25;
      const initialY = random(`${dropSeed}-initY`) * clipH;
      const xOffset = random(`${dropSeed}-x`) * clipW;

      // Tọa độ y cuốn theo frame
      const currentY = clipY + ((initialY + frame * speed) % clipH);
      // Mưa hơi xiên theo gió (độ dốc x = 0.25y)
      const currentX = clipX + ((xOffset + frame * 4) % clipW);

      ctx.beginPath();
      ctx.moveTo(currentX, currentY);
      ctx.lineTo(currentX + 3, currentY + length);
      ctx.stroke();
    }

    ctx.restore();
  }, [frame, width, height, rain, rainRegion]);

  // 2. Đèn lập lòe (flicker) bằng noise2D (biên độ <= 5%)
  let flickerOpacity = 0;
  if (flicker) {
    const n = noise2D("candle-flicker", frame * 0.08, 0.5);
    // n nằm trong [-1, 1], chuẩn hóa biên độ dao động khoảng 0.02 - 0.05
    flickerOpacity = Math.max(0, 0.03 + n * 0.025);
  }

  return (
    <div className="absolute inset-0 w-full h-full pointer-events-none overflow-hidden">
      {/* Lớp mưa canvas */}
      {rain !== "off" && (
        <canvas
          ref={canvasRef}
          width={width}
          height={height}
          className="absolute inset-0 w-full h-full pointer-events-none"
        />
      )}

      {/* Lớp ánh sáng lập lòe của bóng đèn */}
      {flicker && (
        <div
          className="absolute inset-0 pointer-events-none transition-opacity"
          style={{
            background:
              "radial-gradient(circle at 75% 35%, rgba(255, 190, 80, 0.6) 0%, rgba(255, 140, 20, 0.15) 50%, transparent 80%)",
            opacity: flickerOpacity,
            mixBlendMode: "screen",
          }}
        />
      )}
    </div>
  );
};
