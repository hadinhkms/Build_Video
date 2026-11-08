import { interpolate } from "remotion";

export interface BgmDuckingConfig {
  volume: number;
  duckedVolume: number;
  duckIntervals: [number, number][];
  cutAtSec: number | null;
  attackSec?: number;
  releaseSec?: number;
  cutFadeSec?: number;
}

/**
 * Tính âm lượng BGM tại giây timeSec có ducking khi có giọng đọc và ngắt tại cutAtSec.
 * Hàm thuần (pure function) đảm bảo render tất định.
 */
export function calculateBgmVolume(
  timeSec: number,
  config: BgmDuckingConfig
): number {
  const {
    volume,
    duckedVolume,
    duckIntervals,
    cutAtSec,
    attackSec = 0.15,
    releaseSec = 0.5,
    cutFadeSec = 0.3,
  } = config;

  // 1. Tắt nhạc ở Cliffhanger nếu có cutAtSec
  if (cutAtSec !== null && timeSec >= cutAtSec) {
    if (timeSec >= cutAtSec + cutFadeSec) {
      return 0.0;
    }
    const fadeRatio = interpolate(
      timeSec,
      [cutAtSec, cutAtSec + cutFadeSec],
      [1.0, 0.0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );
    // Tính âm lượng nếu không bị cắt rồi nhân với fadeRatio
    const unmuted = getDuckedVolumeAt(timeSec, volume, duckedVolume, duckIntervals, attackSec, releaseSec);
    return Math.round(unmuted * fadeRatio * 1000) / 1000;
  }

  const vol = getDuckedVolumeAt(timeSec, volume, duckedVolume, duckIntervals, attackSec, releaseSec);
  return Math.round(vol * 1000) / 1000;
}

function getDuckedVolumeAt(
  timeSec: number,
  volume: number,
  duckedVolume: number,
  duckIntervals: [number, number][],
  attackSec: number,
  releaseSec: number
): number {
  let minVol = volume;

  for (const [start, end] of duckIntervals) {
    if (timeSec >= start - attackSec && timeSec <= end + releaseSec) {
      let currentVol = volume;
      if (timeSec < start) {
        // Attack: giảm dần từ volume xuống duckedVolume
        currentVol = interpolate(
          timeSec,
          [start - attackSec, start],
          [volume, duckedVolume],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );
      } else if (timeSec <= end) {
        // Trong khoảng thoại: duy trì duckedVolume
        currentVol = duckedVolume;
      } else {
        // Release: hồi phục dần từ duckedVolume về volume
        currentVol = interpolate(
          timeSec,
          [end, end + releaseSec],
          [duckedVolume, volume],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );
      }
      minVol = Math.min(minVol, currentVol);
    }
  }

  return minVol;
}
