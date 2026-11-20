import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { bundle } from "@remotion/bundler";
import {
  renderMedia,
  selectComposition,
  type RenderMediaOptions,
} from "@remotion/renderer";
import { enableTailwind } from "@remotion/tailwind-v4";
import { getOrCreateBundle } from "./bundle-cache";
import {
  findSystemFfmpegDir,
  isNvencRuntimeError,
  prepareRemotionNvencBridge,
  type NvencBridgeResult,
} from "./ffmpeg-bridge";

type GlRenderer = NonNullable<
  NonNullable<RenderMediaOptions["chromiumOptions"]>["gl"]
>;
type X264Preset = NonNullable<RenderMediaOptions["x264Preset"]>;
type ImageFormat = NonNullable<RenderMediaOptions["imageFormat"]>;
type EncoderMode = "auto" | "nvenc" | "libx264";

interface ParsedArgs {
  propsPath?: string;
  outPath?: string;
  concurrencyArg?: string;
  crfArg?: string;
  gl: GlRenderer;
  x264Preset?: X264Preset;
  imageFormat: ImageFormat;
  jpegQuality: number;
  frames?: string;
  scratchDir?: string;
  chapterId?: string;
  noBundleCache: boolean;
  encoder: EncoderMode;
  nvencPreset: string;
  nvencCq?: number;
  ffmpegBinDir?: string;
  nvencBframes: boolean;
  mediaCacheBytes?: number;
  offthreadVideoCacheBytes?: number;
  offthreadVideoThreads?: number;
}

const VALID_GL = new Set<string>([
  "angle",
  "angle-egl",
  "egl",
  "swiftshader",
  "swangle",
  "vulkan",
]);

const VALID_X264_PRESETS = new Set<string>([
  "ultrafast",
  "superfast",
  "veryfast",
  "faster",
  "fast",
  "medium",
  "slow",
  "slower",
  "veryslow",
  "placebo",
]);

const VALID_NVENC_PRESETS = new Set<string>([
  "p1",
  "p2",
  "p3",
  "p4",
  "p5",
  "p6",
  "p7",
]);

function parseCliArgs(argv: string[]): ParsedArgs {
  const positionals: string[] = [];
  const parsed: ParsedArgs = {
    gl: "angle",
    imageFormat: "jpeg",
    jpegQuality: 85,
    noBundleCache: false,
    encoder: "auto",
    nvencPreset: "p5",
    nvencBframes: true,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) {
      positionals.push(token);
      continue;
    }

    let flag = token;
    let inlineVal: string | undefined;
    const eqIdx = token.indexOf("=");
    if (eqIdx !== -1) {
      flag = token.slice(0, eqIdx);
      inlineVal = token.slice(eqIdx + 1);
    }

    const consumeValue = (): string => {
      if (inlineVal !== undefined) {
        return inlineVal;
      }
      const next = argv[i + 1];
      if (next === undefined || next.startsWith("--")) {
        throw new Error(`Missing value for flag ${flag}`);
      }
      i += 1;
      return next;
    };

    switch (flag) {
      case "--props":
        parsed.propsPath = consumeValue();
        break;
      case "--out":
        parsed.outPath = consumeValue();
        break;
      case "--concurrency":
        parsed.concurrencyArg = consumeValue();
        break;
      case "--crf":
        parsed.crfArg = consumeValue();
        break;
      case "--gl": {
        const val = consumeValue();
        if (!VALID_GL.has(val)) {
          throw new Error(`Invalid --gl value: ${val}`);
        }
        parsed.gl = val as GlRenderer;
        break;
      }
      case "--x264-preset": {
        const val = consumeValue();
        if (!VALID_X264_PRESETS.has(val)) {
          throw new Error(`Invalid --x264-preset value: ${val}`);
        }
        parsed.x264Preset = val as X264Preset;
        break;
      }
      case "--image-format": {
        const val = consumeValue();
        if (val !== "jpeg" && val !== "png") {
          throw new Error(`Invalid --image-format value: ${val}`);
        }
        parsed.imageFormat = val;
        break;
      }
      case "--jpeg-quality": {
        const num = Number(consumeValue());
        if (!Number.isFinite(num) || num < 1 || num > 100) {
          throw new Error(`Invalid --jpeg-quality value: ${num}`);
        }
        parsed.jpegQuality = Math.round(num);
        break;
      }
      case "--frames":
        parsed.frames = consumeValue();
        break;
      case "--scratch-dir":
        parsed.scratchDir = consumeValue();
        break;
      case "--chapter-id":
        parsed.chapterId = consumeValue();
        break;
      case "--no-bundle-cache":
        parsed.noBundleCache = true;
        break;
      case "--encoder": {
        const raw = consumeValue().trim().toLowerCase();
        if (raw === "auto" || raw === "nvenc" || raw === "h264_nvenc" || raw === "libx264") {
          parsed.encoder = raw === "h264_nvenc" ? "nvenc" : raw;
        } else {
          throw new Error(`Invalid --encoder value: ${raw}`);
        }
        break;
      }
      case "--nvenc-preset": {
        const val = consumeValue().trim().toLowerCase();
        if (!VALID_NVENC_PRESETS.has(val)) {
          throw new Error(`Invalid --nvenc-preset value: ${val}`);
        }
        parsed.nvencPreset = val;
        break;
      }
      case "--nvenc-cq": {
        const num = Number(consumeValue());
        if (!Number.isFinite(num) || num < 1 || num > 51) {
          throw new Error(`Invalid --nvenc-cq value: ${num}`);
        }
        parsed.nvencCq = Math.round(num);
        break;
      }
      case "--ffmpeg-bin-dir":
        parsed.ffmpegBinDir = consumeValue();
        break;
      case "--nvenc-bframes": {
        const raw = consumeValue().trim().toLowerCase();
        if (raw === "1" || raw === "true") {
          parsed.nvencBframes = true;
        } else if (raw === "0" || raw === "false") {
          parsed.nvencBframes = false;
        } else {
          throw new Error(`Invalid --nvenc-bframes value: ${raw}`);
        }
        break;
      }
      case "--media-cache-bytes": {
        const num = Number(consumeValue());
        if (!Number.isFinite(num) || num <= 0) {
          throw new Error(`Invalid --media-cache-bytes value: ${num}`);
        }
        parsed.mediaCacheBytes = Math.round(num);
        break;
      }
      case "--offthread-video-cache-bytes": {
        const num = Number(consumeValue());
        if (!Number.isFinite(num) || num <= 0) {
          throw new Error(`Invalid --offthread-video-cache-bytes value: ${num}`);
        }
        parsed.offthreadVideoCacheBytes = Math.round(num);
        break;
      }
      case "--offthread-video-threads": {
        const num = Number(consumeValue());
        if (!Number.isFinite(num) || num < 1) {
          throw new Error(`Invalid --offthread-video-threads value: ${num}`);
        }
        parsed.offthreadVideoThreads = Math.max(1, Math.min(16, Math.round(num)));
        break;
      }
      default:
        throw new Error(`Unknown flag: ${flag}`);
    }
  }

  // Giữ tương thích ngược tham số vị trí: <propsPath> <outPath> [concurrency|auto] [crf]
  if (!parsed.propsPath && positionals[0]) parsed.propsPath = positionals[0];
  if (!parsed.outPath && positionals[1]) parsed.outPath = positionals[1];
  if (!parsed.concurrencyArg && positionals[2]) parsed.concurrencyArg = positionals[2];
  if (!parsed.crfArg && positionals[3]) parsed.crfArg = positionals[3];

  return parsed;
}

function parseFrameRange(
  framesSpec: string | undefined,
  durationInFrames: number
): [number, number] | number | null {
  if (!framesSpec) {
    return null;
  }
  const trimmed = framesSpec.trim();
  if (!trimmed) {
    return null;
  }
  const maxFrame = Math.max(0, durationInFrames - 1);
  if (trimmed.includes("-")) {
    const parts = trimmed.split("-");
    if (parts.length !== 2) {
      throw new Error(`Invalid --frames range: ${framesSpec}`);
    }
    const startRaw = parts[0].trim();
    const endRaw = parts[1].trim();
    if (!/^\d+$/.test(startRaw) || !/^\d+$/.test(endRaw)) {
      throw new Error(`Invalid --frames range: ${framesSpec}`);
    }
    const start = Number(startRaw);
    const end = Number(endRaw);
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start) {
      throw new Error(`Invalid --frames range: ${framesSpec}`);
    }
    const clampedStart = Math.min(start, maxFrame);
    const clampedEnd = Math.min(end, maxFrame);
    return [clampedStart, Math.max(clampedStart, clampedEnd)];
  }
  if (!/^\d+$/.test(trimmed)) {
    throw new Error(`Invalid --frames value: ${framesSpec}`);
  }
  const single = Number(trimmed);
  if (!Number.isInteger(single) || single < 0) {
    throw new Error(`Invalid --frames value: ${framesSpec}`);
  }
  return Math.min(single, maxFrame);
}

async function main() {
  const args = parseCliArgs(process.argv.slice(2));
  if (!args.propsPath || !args.outPath) {
    console.error(
      "Usage: tsx scripts/render.ts <propsPath> <outPath> [concurrency|auto] [crf] [--gl angle|swangle] [--x264-preset faster] [--image-format jpeg|png] [--jpeg-quality 85] [--frames 0-239] [--scratch-dir <path>] [--chapter-id <id>] [--no-bundle-cache]"
    );
    process.exit(1);
  }

  const resolvedPropsPath = path.resolve(args.propsPath);
  const resolvedOutPath = path.resolve(args.outPath);

  if (!fs.existsSync(resolvedPropsPath)) {
    console.error(`Error: Props file not found at ${resolvedPropsPath}`);
    process.exit(1);
  }

  const rawProps = fs.readFileSync(resolvedPropsPath, "utf8");
  const inputProps = JSON.parse(rawProps);

  const concurrency =
    args.concurrencyArg === undefined ||
    args.concurrencyArg === "auto" ||
    args.concurrencyArg === "null" ||
    args.concurrencyArg === ""
      ? null
      : Number(args.concurrencyArg);

  const crf = args.crfArg ? Number(args.crfArg) : 18;
  const chapterId =
    args.chapterId ||
    (typeof inputProps?.chapterId === "string" ? inputProps.chapterId : null);

  const remotionDir = path.resolve(__dirname, "..");
  const effectiveScratchDir = args.scratchDir
    ? path.resolve(args.scratchDir)
    : path.resolve(remotionDir, "..", "cache", "scratch");
  let serveUrl: string;
  let bundleMs = 0;

  if (args.noBundleCache) {
    console.log("Bundling Remotion project with Tailwind v4 (bundle cache disabled)...");
    const tBundle0 = performance.now();
    serveUrl = await bundle({
      entryPoint: path.resolve(remotionDir, "src/index.ts"),
      webpackOverride: enableTailwind,
    });
    bundleMs = Math.round(performance.now() - tBundle0);
    console.log(`BUNDLE_CACHE hit=0 hash=disabled sync_ms=0 synced_files=0`);
  } else {
    const cacheRoot = effectiveScratchDir;
    console.log(
      `Bundling Remotion project (cacheRoot=${cacheRoot}, chapter=${chapterId ?? "all"})...`
    );
    const cacheRes = await getOrCreateBundle({
      remotionDir,
      cacheRoot,
      chapterId,
    });
    serveUrl = cacheRes.serveUrl;
    bundleMs = cacheRes.bundleMs;
    console.log(
      `BUNDLE_CACHE hit=${cacheRes.cacheHit ? 1 : 0} hash=${cacheRes.sourceHash} sync_ms=${cacheRes.syncMs} synced_files=${cacheRes.syncedFiles}`
    );
  }

  console.log("Selecting composition 'StoryComposition'...");
  const tSelect0 = performance.now();
  const composition = await selectComposition({
    serveUrl,
    id: "StoryComposition",
    inputProps,
    chromiumOptions: {
      gl: args.gl,
    },
  });
  const selectMs = Math.round(performance.now() - tSelect0);

  const frameRange = parseFrameRange(args.frames, composition.durationInFrames);
  const codec = resolvedOutPath.toLowerCase().endsWith(".mp4")
    ? "h264"
    : "h264-mkv";

  const effectiveNvencCq = args.nvencCq ?? Math.min(51, crf + 1);
  let nvencBridge: NvencBridgeResult | null = null;
  if (args.encoder === "nvenc" || args.encoder === "auto") {
    const sysFfmpegDir = args.ffmpegBinDir || findSystemFfmpegDir();
    if (sysFfmpegDir) {
      nvencBridge = prepareRemotionNvencBridge({
        scratchDir: effectiveScratchDir,
        systemFfmpegDir: sysFfmpegDir,
        nvencPreset: args.nvencPreset,
        cq: effectiveNvencCq,
        supportsBframes: args.nvencBframes,
      });
    } else {
      console.warn("NVENC_BRIDGE_DISABLED reason=system_ffmpeg_not_found");
    }
  }

  const frameSummary = Array.isArray(frameRange)
    ? `${frameRange[0]}-${frameRange[1]} (${frameRange[1] - frameRange[0] + 1}/${composition.durationInFrames} frames)`
    : frameRange !== null
      ? `frame ${frameRange}`
      : `${composition.durationInFrames} frames`;

  fs.mkdirSync(path.dirname(resolvedOutPath), { recursive: true });

  const totalRamGb = os.totalmem() / (1024 ** 3);
  const defaultMediaCacheBytes =
    totalRamGb >= 32
      ? 2 * 1024 * 1024 * 1024
      : totalRamGb >= 16
        ? 1024 * 1024 * 1024
        : 512 * 1024 * 1024;
  const defaultOffthreadCacheBytes =
    totalRamGb >= 32
      ? 1024 * 1024 * 1024
      : totalRamGb >= 16
        ? 512 * 1024 * 1024
        : 256 * 1024 * 1024;

  const mediaCacheSizeInBytes = args.mediaCacheBytes ?? defaultMediaCacheBytes;
  const offthreadVideoCacheSizeInBytes =
    args.offthreadVideoCacheBytes ?? defaultOffthreadCacheBytes;
  const offthreadVideoThreads = args.offthreadVideoThreads ?? 4;

  const baseRenderOptions: RenderMediaOptions = {
    composition,
    serveUrl,
    inputProps,
    codec,
    crf,
    pixelFormat: "yuv420p",
    imageFormat: args.imageFormat,
    ...(args.imageFormat === "jpeg" ? { jpegQuality: args.jpegQuality } : {}),
    ...(args.x264Preset ? { x264Preset: args.x264Preset } : {}),
    ...(frameRange !== null ? { frameRange } : {}),
    concurrency,
    mediaCacheSizeInBytes,
    offthreadVideoCacheSizeInBytes,
    offthreadVideoThreads,
    timeoutInMilliseconds: 120000,
    chromiumOptions: {
      gl: args.gl,
    },
    outputLocation: resolvedOutPath,
    onProgress: ({ progress }) => {
      console.log(`PROGRESS ${progress.toFixed(3)}`);
    },
  };

  let activeEncoder: "h264_nvenc" | "libx264" = nvencBridge ? "h264_nvenc" : "libx264";
  const tRender0 = performance.now();

  if (nvencBridge) {
    console.log(
      `Rendering media: ${composition.width}x${composition.height} @ ${composition.fps}fps, ${frameSummary} (codec=${codec}, encoder=h264_nvenc, preset=${nvencBridge.nvencPreset}, cq=${nvencBridge.cq}, bf=${nvencBridge.supportsBframes ? 2 : 0}, concurrency=${concurrency ?? "auto"}, gl=${args.gl}, fmt=${args.imageFormat})...`
    );
    console.log(
      `ENCODER_ACTIVE h264_nvenc preset=${nvencBridge.nvencPreset} cq=${nvencBridge.cq} bframes=${nvencBridge.supportsBframes ? 2 : 0} bridge_cache=${nvencBridge.reusedCache ? "hit" : "miss"}`
    );
    try {
      await renderMedia({
        ...baseRenderOptions,
        binariesDirectory: nvencBridge.binariesDirectory,
        ffmpegOverride: nvencBridge.ffmpegOverride,
      });
    } catch (err) {
      if (!isNvencRuntimeError(err)) {
        throw err;
      }
      const errMsg = err instanceof Error ? err.message : String(err);
      console.warn(
        `[Warning] NVENC runtime failure detected (${errMsg.slice(0, 200)}). Retrying once with bundled libx264 (preset=faster)...`
      );
      activeEncoder = "libx264";
      const fallbackPreset: X264Preset = args.x264Preset ?? "faster";
      console.log(`ENCODER_ACTIVE libx264 fallback=nvenc_runtime_error preset=${fallbackPreset}`);
      await renderMedia({
        ...baseRenderOptions,
        x264Preset: fallbackPreset,
      });
    }
  } else {
    console.log(
      `Rendering media: ${composition.width}x${composition.height} @ ${composition.fps}fps, ${frameSummary} (codec=${codec}, encoder=libx264, concurrency=${concurrency ?? "auto"}, gl=${args.gl}, preset=${args.x264Preset ?? "default"}, crf=${crf}, fmt=${args.imageFormat})...`
    );
    console.log(
      `ENCODER_ACTIVE libx264 preset=${args.x264Preset ?? "default"} crf=${crf}`
    );
    await renderMedia(baseRenderOptions);
  }

  const renderMs = Math.round(performance.now() - tRender0);

  console.log(
    `TIMING bundle_ms=${bundleMs} select_ms=${selectMs} render_ms=${renderMs} encoder=${activeEncoder}`
  );
  console.log(`RENDER_COMPLETE ${resolvedOutPath}`);
}

main().catch((err) => {
  console.error("RENDER_ERROR:", err);
  process.exit(1);
});
