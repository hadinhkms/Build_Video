import { random } from "remotion";
import { noise2D } from "@remotion/noise";

/**
 * Thở: tính chu kỳ theo giây, biên độ nhỏ (<= 0.8%), chỉ scaleY phần thân (transform-origin: bottom center).
 * @param t Thời gian tính bằng giây từ đầu cảnh (frame / fps).
 * @param act Hồi kịch bản (HOOK, SETUP, RISING, CLIMAX, CLIFFHANGER).
 * @returns Hệ số co giãn scaleY (trong khoảng 0.992 đến 1.008).
 */
export function breathScale(t: number, act: string): number {
  const period = act === "CLIMAX" ? 2.5 : 4.0;
  return 1 + 0.008 * Math.sin((2 * Math.PI * t) / period);
}

/**
 * Lấy danh sách thời điểm chớp mắt (tính bằng giây) trong khoảng [0, maxDurationSec].
 * Mỗi khoảng cách giữa 2 lần chớp liên tiếp là ngẫu nhiên tất định trong [2.5, 5.0] giây.
 */
export function getBlinkTimings(maxDurationSec: number, seed: string): number[] {
  const timings: number[] = [];
  let at = 0.8 + random(`${seed}-0`) * 2.0; // Lần chớp đầu tiên: 0.8s - 2.8s
  let i = 1;
  while (at <= maxDurationSec) {
    timings.push(at);
    at += 2.5 + random(`${seed}-${i}`) * 2.5; // Khoảng cách: 2.5s - 5.0s
    i++;
  }
  return timings;
}

/**
 * Chớp mắt: khoảng cách ngẫu nhiên tất định 2,5–5 s; mỗi lần chớp ~120 ms.
 * @param t Thời gian tính bằng giây từ đầu cảnh.
 * @param seed Chuỗi hạt giống tất định (ví dụ: `${characterId}-${sceneId}`).
 * @returns 0..1 = độ phủ của patch mắt nhắm (đóng rồi mở theo hình tam giác).
 */
export function blinkAmount(t: number, seed: string): number {
  if (t < 0) return 0;
  let at = 0.8 + random(`${seed}-0`) * 2.0;
  for (let i = 1; ; i++) {
    if (t < at) {
      return 0;
    }
    const d = t - at;
    if (d < 0.12) {
      // Đóng rồi mở theo hình tam giác: peak tại 0.06s (120ms tổng thời lượng)
      return 1 - Math.abs(d - 0.06) / 0.06;
    }
    at += 2.5 + random(`${seed}-${i}`) * 2.5;
  }
}

/**
 * Chuyển động vi mô của đầu (micro head drift):
 * xoay ±0,4° và dịch ±3 px theo Perlin/Simplex noise tất định của Remotion.
 * @param t Thời gian tính bằng giây.
 * @param seed Hạt giống tất định.
 */
export function headDrift(
  t: number,
  seed: string
): { rotateDeg: number; translateX: number; translateY: number } {
  const rot = noise2D(`${seed}-rot`, t * 0.4, 0) * 0.4;
  const tx = noise2D(`${seed}-tx`, t * 0.4, 0) * 3.0;
  const ty = noise2D(`${seed}-ty`, t * 0.4, 0) * 3.0;
  return {
    rotateDeg: Math.max(-0.4, Math.min(0.4, rot)),
    translateX: Math.max(-3.0, Math.min(3.0, tx)),
    translateY: Math.max(-3.0, Math.min(3.0, ty)),
  };
}
