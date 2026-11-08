import { Easing, interpolate } from "remotion";

export type CameraMotion =
  | "zoom_in"
  | "rapid_zoom_in"
  | "zoom_out"
  | "pan_left"
  | "pan_right"
  | "static";

// [scale đầu, scale cuối, x đầu, x cuối]; x tính theo tỉ lệ bề rộng khung (0.01 = 1%)
const MOVES: Record<CameraMotion, [number, number, number, number]> = {
  zoom_in:       [1.00, 1.12,  0.00,  0.00],
  rapid_zoom_in: [1.00, 1.25,  0.00,  0.00],
  zoom_out:      [1.12, 1.00,  0.00,  0.00],
  pan_left:      [1.10, 1.10,  0.03, -0.03], // di chuyển từ phải sang trái (camera lia sang trái)
  pan_right:     [1.10, 1.10, -0.03,  0.03],
  static:        [1.04, 1.04,  0.00,  0.00],
};

/**
 * Tính toán scale và độ dịch chuyển xPercent cho hiệu ứng camera điện ảnh kèm parallax 2.5D.
 * @param motion Kiểu chuyển động camera
 * @param frame Frame hiện tại trong cảnh
 * @param duration Tổng số frame của cảnh
 * @param depth Độ sâu: plate = 1.0, nhân vật = 1.35, tiền cảnh = 0
 */
export function cameraTransform(
  motion: CameraMotion,
  frame: number,
  duration: number,
  depth = 1.0
) {
  const easing =
    motion === "rapid_zoom_in" ? Easing.out(Easing.cubic) : Easing.inOut(Easing.sin);

  const t = interpolate(frame, [0, Math.max(1, duration - 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing,
  });

  const [s0, s1, x0, x1] = MOVES[motion] || MOVES.static;

  return {
    scale: 1 + (interpolate(t, [0, 1], [s0, s1]) - 1) * depth,
    xPercent: interpolate(t, [0, 1], [x0, x1]) * depth * 100,
  };
}
