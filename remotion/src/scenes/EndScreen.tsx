import React from "react";
import { Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { Scene } from "../schemas/render-props";

export interface EndScreenProps {
  scene: Scene;
}

export const EndScreen: React.FC<EndScreenProps> = ({ scene }) => {
  const frame = useCurrentFrame();

  const src = scene.visual.imageSrc || scene.visual.backgroundSrc;
  const resolvedSrc = src ? staticFile(src) : null;

  // Zoom chậm từ 1.0 đến 1.05
  const bgScale = interpolate(frame, [0, scene.durationInFrames], [1.0, 1.06], {
    extrapolateRight: "clamp",
  });

  return (
    <div className="relative w-full h-full overflow-hidden bg-black flex flex-col justify-between p-16">
      {/* Nền ảnh tối và zoom nhẹ */}
      {resolvedSrc && (
        <div
          className="absolute inset-0 pointer-events-none will-change-transform"
          style={{ transform: `scale(${bgScale})` }}
        >
          <Img
            src={resolvedSrc}
            className="w-full h-full object-cover filter brightness-[0.20] saturate-50"
            alt="end screen background"
          />
        </div>
      )}

      {/* Thông điệp kết thúc */}
      <div className="relative z-10 text-left pt-6" style={{ fontFamily: "var(--font-cinema), sans-serif" }}>
        <h2 className="text-amber-400 text-2xl font-bold tracking-[0.25em] uppercase mb-2">
          Theo Dõi Chương Tiếp Theo
        </h2>
        <p className="text-gray-300 text-lg max-w-xl leading-relaxed">
          Đăng ký kênh để không bỏ lỡ những diễn biến kịch tính tiếp theo.
        </p>
      </div>

      {/* Vùng an toàn để YouTube gắn End Screen Elements (Thẻ video & Nút đăng ký) */}
      <div className="relative z-10 w-full flex justify-end items-center gap-8 pb-8 pr-8 pointer-events-none">
        {/* Placeholder khung video tiếp theo */}
        <div className="w-[420px] h-[236px] rounded-xl border border-white/20 bg-white/5 backdrop-brightness-50 flex items-center justify-center text-gray-400 text-sm">
          <span>Khung hiển thị Video tiếp theo</span>
        </div>
      </div>
    </div>
  );
};
