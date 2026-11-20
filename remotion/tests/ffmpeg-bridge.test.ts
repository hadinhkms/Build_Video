import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  buildNvencOverride,
  findDllCollisions,
  isNvencRuntimeError,
  prepareRemotionNvencBridge,
} from "../scripts/ffmpeg-bridge";

describe("ffmpeg-bridge", () => {
  it("buildNvencOverride rewrites pre-stitcher libx264 args and preserves pixelFormat & timescale", () => {
    const override = buildNvencOverride({
      nvencPreset: "p5",
      cq: 19,
      supportsBframes: true,
    });

    const inputArgs = [
      "-r",
      "24",
      "-f",
      "image2pipe",
      "-s",
      "1920x1080",
      "-vcodec",
      "mjpeg",
      "-i",
      "-",
      "-c:v",
      "libx264",
      "-pix_fmt",
      "yuv420p",
      "-preset",
      "veryfast",
      "-video_track_timescale",
      "90000",
      "-crf",
      "18",
      "-y",
      "out.mkv",
    ];

    const out = override({ type: "pre-stitcher", args: inputArgs });
    expect(out).toContain("h264_nvenc");
    expect(out).not.toContain("libx264");
    expect(out).not.toContain("-crf");
    expect(out).not.toContain("veryfast");

    expect(out[out.indexOf("-c:v") + 1]).toBe("h264_nvenc");
    expect(out[out.indexOf("-preset") + 1]).toBe("p5");
    expect(out[out.indexOf("-tune") + 1]).toBe("hq");
    expect(out[out.indexOf("-rc") + 1]).toBe("vbr");
    expect(out[out.indexOf("-cq") + 1]).toBe("19");
    expect(out[out.indexOf("-b:v") + 1]).toBe("0");
    expect(out[out.indexOf("-spatial-aq") + 1]).toBe("1");
    expect(out[out.indexOf("-aq-strength") + 1]).toBe("8");
    expect(out[out.indexOf("-bf") + 1]).toBe("2");
    expect(out[out.indexOf("-pix_fmt") + 1]).toBe("yuv420p");
    expect(out[out.indexOf("-video_track_timescale") + 1]).toBe("90000");
    expect(out[out.length - 1]).toBe("out.mkv");
  });

  it("buildNvencOverride sets -bf 0 when supportsBframes is false", () => {
    const override = buildNvencOverride({
      nvencPreset: "p4",
      cq: 20,
      supportsBframes: false,
    });
    const out = override({
      type: "pre-stitcher",
      args: ["-i", "-", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "out.mkv"],
    });
    expect(out[out.indexOf("-bf") + 1]).toBe("0");
    expect(out[out.indexOf("-preset") + 1]).toBe("p4");
    expect(out[out.indexOf("-cq") + 1]).toBe("20");
  });

  it("buildNvencOverride leaves stitcher -c:v copy and PCM audio 100% untouched", () => {
    const override = buildNvencOverride({ nvencPreset: "p5", cq: 19, supportsBframes: true });
    const stitcherArgs = [
      "-i",
      "video_pre.mkv",
      "-i",
      "audio.wav",
      "-c:v",
      "copy",
      "-c:a",
      "pcm_s16le",
      "-y",
      "video.prenorm.mkv",
    ];
    const out = override({ type: "stitcher", args: stitcherArgs });
    expect(out).toEqual(stitcherArgs);
  });

  it("findDllCollisions detects case-insensitive collisions and prepareRemotionNvencBridge returns null", () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "hw-bridge-test-"));
    try {
      const compDir = path.join(tmp, "comp");
      const sysDir = path.join(tmp, "sys");
      const scratchDir = path.join(tmp, "scratch");
      fs.mkdirSync(compDir, { recursive: true });
      fs.mkdirSync(sysDir, { recursive: true });

      fs.writeFileSync(path.join(compDir, "remotion.exe"), "stub");
      fs.writeFileSync(path.join(compDir, "avcodec-61.dll"), "a");
      fs.writeFileSync(path.join(compDir, "avutil-59.dll"), "b");

      fs.writeFileSync(path.join(sysDir, "ffmpeg.exe"), "stub");
      fs.writeFileSync(path.join(sysDir, "ffprobe.exe"), "stub");
      fs.writeFileSync(path.join(sysDir, "avcodec-62.dll"), "c");

      // Không va chạm
      expect(findDllCollisions(compDir, sysDir)).toEqual([]);

      // Gây va chạm khác chữ hoa/thường
      fs.writeFileSync(path.join(sysDir, "AVCODEC-61.DLL"), "conflict");
      const collisions = findDllCollisions(compDir, sysDir);
      expect(collisions.map((c) => c.toLowerCase())).toEqual(["avcodec-61.dll"]);

      // Bridge phải tự hủy và trả null an toàn
      const bridge = prepareRemotionNvencBridge({
        scratchDir,
        systemFfmpegDir: sysDir,
        compositorDirOverride: compDir,
      });
      expect(bridge).toBeNull();
    } finally {
      fs.rmSync(tmp, { recursive: true, force: true });
    }
  });

  it("isNvencRuntimeError classifies NVENC errors accurately", () => {
    expect(isNvencRuntimeError(new Error("OpenEncodeSessionEx failed: incompatible client key"))).toBe(true);
    expect(isNvencRuntimeError(new Error("Cannot load nvcuda.dll"))).toBe(true);
    expect(isNvencRuntimeError(new Error("Error while opening encoder for output stream: h264_nvenc"))).toBe(true);
    expect(isNvencRuntimeError(new Error("Composition StoryComposition not found"))).toBe(false);
  });

  it("buildNvencOverride handles -vcodec/-codec:v libx264, strips x264-only flags, and keeps input -vcodec mjpeg", () => {
    const override = buildNvencOverride({ nvencPreset: "p5", cq: 22, supportsBframes: true });
    const out = override({
      type: "pre-stitcher",
      args: [
        "-vcodec",
        "mjpeg",
        "-i",
        "-",
        "-vcodec",
        "libx264",
        "-preset:v",
        "medium",
        "-crf",
        "18",
        "-x264-params",
        "keyint=48",
        "-pix_fmt",
        "yuv420p",
        "out.mkv",
      ],
    });
    expect(out[out.indexOf("-vcodec") + 1]).toBe("mjpeg");
    expect(out).toContain("h264_nvenc");
    expect(out).not.toContain("libx264");
    expect(out).not.toContain("-crf");
    expect(out).not.toContain("-preset:v");
    expect(out).not.toContain("-x264-params");
    expect(out[out.indexOf("-cq") + 1]).toBe("22");
  });

  it("prepareRemotionNvencBridge returns null safely when system FFmpeg dir or executable is deleted", () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "hw-bridge-missing-"));
    try {
      const compDir = path.join(tmp, "comp");
      const sysDir = path.join(tmp, "sys_missing");
      fs.mkdirSync(compDir, { recursive: true });
      fs.writeFileSync(path.join(compDir, "remotion.exe"), "stub");

      // Thư mục systemFfmpegDir không tồn tại
      expect(
        prepareRemotionNvencBridge({
          scratchDir: path.join(tmp, "scratch"),
          systemFfmpegDir: sysDir,
          compositorDirOverride: compDir,
        })
      ).toBeNull();

      // Thư mục tồn tại nhưng thiếu ffmpeg.exe
      fs.mkdirSync(sysDir, { recursive: true });
      fs.writeFileSync(path.join(sysDir, "ffprobe.exe"), "stub");
      expect(
        prepareRemotionNvencBridge({
          scratchDir: path.join(tmp, "scratch"),
          systemFfmpegDir: sysDir,
          compositorDirOverride: compDir,
        })
      ).toBeNull();
    } finally {
      fs.rmSync(tmp, { recursive: true, force: true });
    }
  });
});
