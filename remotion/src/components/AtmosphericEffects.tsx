import React, { useEffect, useMemo, useRef } from "react";
import { noise2D } from "@remotion/noise";
import { random, useCurrentFrame, useVideoConfig } from "remotion";
import { Effects } from "../schemas/render-props";

export interface AtmosphericEffectsProps {
  effects: Effects;
  durationInFrames: number;
}

const NUM_DROPS = 180;

interface RainDropParams {
  speed: number;
  length: number;
  initY: number;
  xOffset: number;
}

export const AtmosphericEffects: React.FC<AtmosphericEffectsProps> = ({
  effects,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const prevClipKeyRef = useRef<string | null>(null);

  const { rain, rainRegion, flicker } = effects;

  // Xác định vùng mưa (toàn khung hoặc cửa sổ)
  const isWindowRain = rain === "window" && Boolean(rainRegion);
  const clipX = isWindowRain && rainRegion ? rainRegion.x * width : 0;
  const clipY = isWindowRain && rainRegion ? rainRegion.y * height : 0;
  const clipW = isWindowRain && rainRegion ? rainRegion.w * width : width;
  const clipH = isWindowRain && rainRegion ? rainRegion.h * height : height;

  // Tính sẵn 180 giọt mưa một lần duy nhất (giữ nguyên seed `rain-drop-${i}` -> tất định 100%)
  const rainDrops = useMemo<RainDropParams[]>(() => {
    if (rain === "off" || clipW <= 0 || clipH <= 0) {
      return [];
    }
    const drops = new Array<RainDropParams>(NUM_DROPS);
    for (let i = 0; i < NUM_DROPS; i++) {
      const dropSeed = `rain-drop-${i}`;
      drops[i] = {
        speed: 20 + random(`${dropSeed}-speed`) * 15,
        length: 20 + random(`${dropSeed}-len`) * 25,
        initY: random(`${dropSeed}-initY`) * clipH,
        xOffset: random(`${dropSeed}-x`) * clipW,
      };
    }
    return drops;
  }, [rain, clipW, clipH]);

  // 1. Vẽ mưa tất định bằng canvas trong 1 cặp beginPath()/stroke() duy nhất
  useEffect(() => {
    if (rain === "off") return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const clipKey = `${width}:${height}:${clipX}:${clipY}:${clipW}:${clipH}`;
    if (isWindowRain && prevClipKeyRef.current === clipKey) {
      // Chỉ xóa đúng vùng cửa sổ (có biên an toàn 1px chống sót nét anti-alias)
      const clearX = Math.max(0, Math.floor(clipX) - 1);
      const clearY = Math.max(0, Math.floor(clipY) - 1);
      const clearRight = Math.min(width, Math.ceil(clipX + clipW) + 1);
      const clearBottom = Math.min(height, Math.ceil(clipY + clipH) + 1);
      ctx.clearRect(
        clearX,
        clearY,
        Math.max(0, clearRight - clearX),
        Math.max(0, clearBottom - clearY)
      );
    } else {
      ctx.clearRect(0, 0, width, height);
      prevClipKeyRef.current = clipKey;
    }

    if (clipW <= 0 || clipH <= 0 || rainDrops.length === 0) return;

    ctx.save();
    ctx.beginPath();
    ctx.rect(clipX, clipY, clipW, clipH);
    ctx.clip();

    ctx.lineWidth = 1.2;
    ctx.strokeStyle = "rgba(220, 235, 255, 0.45)";

    ctx.beginPath();
    for (let i = 0; i < rainDrops.length; i++) {
      const drop = rainDrops[i];
      // Tọa độ y cuốn theo frame (chuẩn hóa modulo dương)
      const yMod = ((drop.initY + frame * drop.speed) % clipH + clipH) % clipH;
      const xMod = ((drop.xOffset + frame * 4) % clipW + clipW) % clipW;
      const currentY = clipY + yMod;
      // Mưa hơi xiên theo gió (độ dốc x = 0.25y)
      const currentX = clipX + xMod;

      ctx.moveTo(currentX, currentY);
      ctx.lineTo(currentX + 3, currentY + drop.length);
    }
    ctx.stroke();

    ctx.restore();
  }, [frame, width, height, rain, isWindowRain, clipX, clipY, clipW, clipH, rainDrops]);

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
