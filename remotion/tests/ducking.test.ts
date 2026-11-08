import { describe, it, expect } from "vitest";
import { calculateBgmVolume, BgmDuckingConfig } from "../src/lib/ducking";

describe("calculateBgmVolume", () => {
  const config: BgmDuckingConfig = {
    volume: 0.4,
    duckedVolume: 0.15,
    duckIntervals: [
      [2.0, 5.0],
      [10.0, 14.0],
    ],
    cutAtSec: 20.0,
    attackSec: 0.2,
    releaseSec: 0.5,
  };

  it("should return full volume outside duck intervals", () => {
    expect(calculateBgmVolume(0.5, config)).toBe(0.4);
    expect(calculateBgmVolume(1.5, config)).toBe(0.4);
    expect(calculateBgmVolume(7.0, config)).toBe(0.4);
  });

  it("should return ducked volume inside speech intervals", () => {
    expect(calculateBgmVolume(2.0, config)).toBe(0.15);
    expect(calculateBgmVolume(3.5, config)).toBe(0.15);
    expect(calculateBgmVolume(5.0, config)).toBe(0.15);

    expect(calculateBgmVolume(12.0, config)).toBe(0.15);
  });

  it("should ramp down during attack window", () => {
    // Attack window: [1.8, 2.0]
    const midAttack = calculateBgmVolume(1.9, config);
    expect(midAttack).toBeGreaterThan(0.15);
    expect(midAttack).toBeLessThan(0.4);
  });

  it("should ramp up during release window", () => {
    // Release window: [5.0, 5.5]
    const midRelease = calculateBgmVolume(5.25, config);
    expect(midRelease).toBeGreaterThan(0.15);
    expect(midRelease).toBeLessThan(0.4);
  });

  it("should fade to zero after cutAtSec", () => {
    // cutAtSec = 20.0
    expect(calculateBgmVolume(19.0, config)).toBe(0.4);
    const midFade = calculateBgmVolume(20.15, config);
    expect(midFade).toBeGreaterThan(0.0);
    expect(midFade).toBeLessThan(0.4);

    // After 20.3s (cutFadeSec = 0.3)
    expect(calculateBgmVolume(20.35, config)).toBe(0.0);
    expect(calculateBgmVolume(25.0, config)).toBe(0.0);
  });
});
