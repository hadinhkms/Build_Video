import React from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Caption } from "../schemas/render-props";

export interface SubtitleBoxProps {
  captions: Caption[];
  enabled: boolean;
  bottomOffsetPx?: number;
}

/**
 * Chia văn bản thành các phân đoạn thường và phân đoạn highlight (hỗ trợ cụm nhiều từ).
 */
function renderHighlightedText(rawText: string, highlights: string[]) {
  if (!highlights || highlights.length === 0) {
    return <span>{rawText}</span>;
  }

  const normalizedText = rawText.normalize("NFC");
  const lowerText = normalizedText.toLowerCase();

  // Tìm các khoảng ký tự [start, end] được highlight
  const ranges: [number, number][] = [];
  for (const hl of highlights) {
    const cleanHl = hl.normalize("NFC").trim().toLowerCase();
    if (!cleanHl) continue;
    let idx = lowerText.indexOf(cleanHl);
    while (idx !== -1) {
      ranges.push([idx, idx + cleanHl.length]);
      idx = lowerText.indexOf(cleanHl, idx + 1);
    }
  }

  if (ranges.length === 0) {
    return <span>{rawText}</span>;
  }

  // Gộp các khoảng chồng lấn
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const r of ranges) {
    if (merged.length === 0) {
      merged.push(r);
    } else {
      const prev = merged[merged.length - 1];
      if (r[0] <= prev[1]) {
        prev[1] = Math.max(prev[1], r[1]);
      } else {
        merged.push(r);
      }
    }
  }

  const nodes: React.ReactNode[] = [];
  let curr = 0;
  for (let i = 0; i < merged.length; i++) {
    const [st, en] = merged[i];
    if (curr < st) {
      nodes.push(<span key={`txt-${curr}`}>{normalizedText.slice(curr, st)}</span>);
    }
    nodes.push(
      <span
        key={`hl-${st}`}
        className="text-amber-300 font-bold drop-shadow-[0_2px_8px_rgba(245,158,11,0.6)]"
      >
        {normalizedText.slice(st, en)}
      </span>
    );
    curr = en;
  }
  if (curr < normalizedText.length) {
    nodes.push(<span key={`txt-${curr}`}>{normalizedText.slice(curr)}</span>);
  }

  return <>{nodes}</>;
}

export const SubtitleBox: React.FC<SubtitleBoxProps> = ({
  captions,
  enabled,
  bottomOffsetPx = 160,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (!enabled || !captions || captions.length === 0) {
    return null;
  }

  const t = frame / fps;
  const cap = captions.find((c) => t >= c.start && t < c.end);
  if (!cap) {
    return null;
  }

  // Hiệu ứng spring pop-in mượt mà khi cụm phụ đề xuất hiện
  const localFrame = frame - Math.round(cap.start * fps);
  const popScale = spring({
    frame: localFrame,
    fps,
    config: { damping: 14, stiffness: 140, mass: 0.6 },
  });

  return (
    <div
      className="absolute left-0 right-0 flex justify-center items-center pointer-events-none z-30"
      style={{ bottom: `${bottomOffsetPx}px` }}
    >
      <div
        className="px-6 py-2.5 rounded-full bg-black/75 border border-white/10 shadow-2xl text-center will-change-transform max-w-[85%]"
        style={{
          transform: `scale(${popScale})`,
          fontFamily: "var(--font-cinema), sans-serif",
          fontSize: "38px",
          lineHeight: "1.3",
          letterSpacing: "0.01em",
        }}
      >
        <span className="text-white font-semibold">
          {renderHighlightedText(cap.text, cap.highlight)}
        </span>
      </div>
    </div>
  );
};
