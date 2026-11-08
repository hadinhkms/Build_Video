import { describe, it, expect } from "vitest";
import { breathScale, blinkAmount, headDrift, getBlinkTimings } from "../src/lib/life";

describe("Character Life System (lib/life.ts)", () => {
  const seed = "char_01-scene_01";

  it("should have breath scale amplitude <= 0.8% and correct periods", () => {
    // Normal period = 4.0s
    for (let t = 0; t <= 10; t += 0.1) {
      const scaleNormal = breathScale(t, "SETUP");
      expect(scaleNormal).toBeGreaterThanOrEqual(1 - 0.008);
      expect(scaleNormal).toBeLessThanOrEqual(1 + 0.008);
    }

    // Climax period = 2.5s
    for (let t = 0; t <= 10; t += 0.1) {
      const scaleClimax = breathScale(t, "CLIMAX");
      expect(scaleClimax).toBeGreaterThanOrEqual(1 - 0.008);
      expect(scaleClimax).toBeLessThanOrEqual(1 + 0.008);
    }

    // At t=0, sin(0) = 0 -> scale = 1.0
    expect(breathScale(0, "SETUP")).toBe(1.0);
    expect(breathScale(0, "CLIMAX")).toBe(1.0);
  });

  it("should have blink intervals strictly between 2.5s and 5.0s", () => {
    const timings = getBlinkTimings(30, seed);
    expect(timings.length).toBeGreaterThan(4);

    for (let i = 1; i < timings.length; i++) {
      const interval = timings[i] - timings[i - 1];
      expect(interval).toBeGreaterThanOrEqual(2.5);
      expect(interval).toBeLessThanOrEqual(5.0);
    }
  });

  it("should have each blink duration within 80ms - 200ms", () => {
    const timings = getBlinkTimings(15, seed);
    const firstBlinkTime = timings[0];

    // Right before blink start
    expect(blinkAmount(firstBlinkTime - 0.001, seed)).toBe(0);

    // Peak at midpoint (~60ms)
    const peak = blinkAmount(firstBlinkTime + 0.06, seed);
    expect(peak).toBeCloseTo(1.0, 2);

    // Right after blink end (120ms total)
    expect(blinkAmount(firstBlinkTime + 0.121, seed)).toBe(0);

    // Measure total duration where blinkAmount > 0
    let activeStart = -1;
    let activeEnd = -1;
    for (let t = firstBlinkTime - 0.05; t <= firstBlinkTime + 0.2; t += 0.005) {
      const amt = blinkAmount(t, seed);
      if (amt > 0) {
        if (activeStart === -1) activeStart = t;
        activeEnd = t;
      }
    }
    const durationMs = (activeEnd - activeStart) * 1000;
    expect(durationMs).toBeGreaterThanOrEqual(80);
    expect(durationMs).toBeLessThanOrEqual(200);
  });

  it("should produce strictly deterministic results for the same seed and time", () => {
    for (let t = 0; t <= 10; t += 0.5) {
      const b1 = blinkAmount(t, seed);
      const b2 = blinkAmount(t, seed);
      expect(b1).toBe(b2);

      const d1 = headDrift(t, seed);
      const d2 = headDrift(t, seed);
      expect(d1.rotateDeg).toBe(d2.rotateDeg);
      expect(d1.translateX).toBe(d2.translateX);
      expect(d1.translateY).toBe(d2.translateY);
    }
  });

  it("should limit head drift within ±0.4 deg and ±3 px", () => {
    for (let t = 0; t <= 20; t += 0.25) {
      const drift = headDrift(t, seed);
      expect(drift.rotateDeg).toBeGreaterThanOrEqual(-0.4);
      expect(drift.rotateDeg).toBeLessThanOrEqual(0.4);
      expect(drift.translateX).toBeGreaterThanOrEqual(-3.0);
      expect(drift.translateX).toBeLessThanOrEqual(3.0);
      expect(drift.translateY).toBeGreaterThanOrEqual(-3.0);
      expect(drift.translateY).toBeLessThanOrEqual(3.0);
    }
  });
});
