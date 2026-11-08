import { describe, it, expect } from "vitest";
import { cameraTransform, CameraMotion } from "../src/lib/camera";

describe("cameraTransform", () => {
  const duration = 100;
  const motions: CameraMotion[] = [
    "zoom_in",
    "rapid_zoom_in",
    "zoom_out",
    "pan_left",
    "pan_right",
    "static",
  ];

  it("should match exact start and end values for all motions at depth 1", () => {
    // zoom_in
    const zInStart = cameraTransform("zoom_in", 0, duration, 1);
    const zInEnd = cameraTransform("zoom_in", duration - 1, duration, 1);
    expect(zInStart.scale).toBeCloseTo(1.0, 3);
    expect(zInEnd.scale).toBeCloseTo(1.12, 3);

    // zoom_out
    const zOutStart = cameraTransform("zoom_out", 0, duration, 1);
    const zOutEnd = cameraTransform("zoom_out", duration - 1, duration, 1);
    expect(zOutStart.scale).toBeCloseTo(1.12, 3);
    expect(zOutEnd.scale).toBeCloseTo(1.0, 3);

    // pan_left
    const pLeftStart = cameraTransform("pan_left", 0, duration, 1);
    const pLeftEnd = cameraTransform("pan_left", duration - 1, duration, 1);
    expect(pLeftStart.scale).toBeCloseTo(1.1, 3);
    expect(pLeftStart.xPercent).toBeCloseTo(3.0, 3);
    expect(pLeftEnd.xPercent).toBeCloseTo(-3.0, 3);

    // pan_right
    const pRightStart = cameraTransform("pan_right", 0, duration, 1);
    const pRightEnd = cameraTransform("pan_right", duration - 1, duration, 1);
    expect(pRightStart.scale).toBeCloseTo(1.1, 3);
    expect(pRightStart.xPercent).toBeCloseTo(-3.0, 3);
    expect(pRightEnd.xPercent).toBeCloseTo(3.0, 3);
  });

  it("should be monotonic across frames", () => {
    // zoom_in scale should never decrease
    let prevScale = 0;
    for (let f = 0; f < duration; f++) {
      const { scale } = cameraTransform("zoom_in", f, duration, 1);
      expect(scale).toBeGreaterThanOrEqual(prevScale);
      prevScale = scale;
    }

    // zoom_out scale should never increase
    let prevOutScale = 999;
    for (let f = 0; f < duration; f++) {
      const { scale } = cameraTransform("zoom_out", f, duration, 1);
      expect(scale).toBeLessThanOrEqual(prevOutScale);
      prevOutScale = scale;
    }

    // pan_left xPercent should never increase
    let prevX = 999;
    for (let f = 0; f < duration; f++) {
      const { xPercent } = cameraTransform("pan_left", f, duration, 1);
      expect(xPercent).toBeLessThanOrEqual(prevX);
      prevX = xPercent;
    }
  });

  it("should never leak edges (offset <= margin)", () => {
    // Margin on each side when scaled by s is (s - 1) / 2 * 100%
    for (const motion of motions) {
      for (let f = 0; f < duration; f += 10) {
        const { scale, xPercent } = cameraTransform(motion, f, duration, 1);
        const marginPercent = ((scale - 1) / 2) * 100;
        // xPercent offset magnitude must not exceed margin
        expect(Math.abs(xPercent)).toBeLessThanOrEqual(marginPercent + 0.001);
      }
    }
  });

  it("should scale displacement with parallax depth", () => {
    const depth1 = cameraTransform("zoom_in", duration - 1, duration, 1.0);
    const depthParallax = cameraTransform("zoom_in", duration - 1, duration, 1.35);

    expect(depthParallax.scale).toBeGreaterThan(depth1.scale);
  });
});
