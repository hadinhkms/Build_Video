import fs from "node:fs";
import path from "node:path";
import { bundle } from "@remotion/bundler";
import {
  openBrowser,
  renderStill,
  selectComposition,
  type RenderStillOptions,
} from "@remotion/renderer";
import { enableTailwind } from "@remotion/tailwind-v4";
import { getOrCreateBundle } from "./bundle-cache";

type GlRenderer = NonNullable<
  NonNullable<RenderStillOptions["chromiumOptions"]>["gl"]
>;
type StillImageFormat = NonNullable<RenderStillOptions["imageFormat"]>;

export interface StillJob {
  id: string;
  frame: number;
  outputPath: string;
}

export interface ParsedStillsArgs {
  propsPath?: string;
  compositionId: string;
  allScenes: boolean;
  outDir?: string;
  frame?: number;
  outPath?: string;
  jobsPath?: string;
  concurrency: number;
  gl: GlRenderer;
  imageFormat: StillImageFormat;
  jpegQuality: number;
  scratchDir?: string;
  chapterId?: string;
  noBundleCache: boolean;
}

const VALID_GL = new Set<string>([
  "angle",
  "angle-egl",
  "egl",
  "swiftshader",
  "swangle",
  "vulkan",
]);

const VALID_STILL_FORMATS = new Set<string>(["png", "jpeg", "webp"]);

export function parseStillsCliArgs(argv: string[]): ParsedStillsArgs {
  const parsed: ParsedStillsArgs = {
    compositionId: "StoryComposition",
    allScenes: false,
    concurrency: 6,
    gl: "angle",
    imageFormat: "png",
    jpegQuality: 90,
    noBundleCache: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) {
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
      case "--composition":
        parsed.compositionId = consumeValue();
        break;
      case "--all-scenes":
        parsed.allScenes = true;
        break;
      case "--out-dir":
        parsed.outDir = consumeValue();
        break;
      case "--frame": {
        const num = Number(consumeValue());
        if (!Number.isFinite(num) || num < 0) {
          throw new Error(`Invalid --frame value: ${num}`);
        }
        parsed.frame = Math.floor(num);
        break;
      }
      case "--out":
        parsed.outPath = consumeValue();
        break;
      case "--jobs":
        parsed.jobsPath = consumeValue();
        break;
      case "--concurrency": {
        const num = Number(consumeValue());
        if (!Number.isFinite(num) || num < 1) {
          throw new Error(`Invalid --concurrency value: ${num}`);
        }
        parsed.concurrency = Math.max(1, Math.min(16, Math.round(num)));
        break;
      }
      case "--gl": {
        const val = consumeValue();
        if (!VALID_GL.has(val)) {
          throw new Error(`Invalid --gl value: ${val}`);
        }
        parsed.gl = val as GlRenderer;
        break;
      }
      case "--image-format": {
        const val = consumeValue().trim().toLowerCase();
        if (!VALID_STILL_FORMATS.has(val)) {
          throw new Error(`Invalid --image-format value: ${val}`);
        }
        parsed.imageFormat = val as StillImageFormat;
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
      case "--scratch-dir":
        parsed.scratchDir = consumeValue();
        break;
      case "--chapter-id":
        parsed.chapterId = consumeValue();
        break;
      case "--no-bundle-cache":
        parsed.noBundleCache = true;
        break;
      default:
        throw new Error(`Unknown flag: ${flag}`);
    }
  }

  return parsed;
}

/**
 * Xây dựng danh sách ảnh still giữa mỗi phân cảnh khớp 100% quy ước đặt tên `<sceneId>_f<midFrame>.png`.
 */
export function buildAllSceneJobs(
  scenes: Array<{ id?: string; durationInFrames?: number }>,
  outDir: string,
  ext = "png"
): StillJob[] {
  const resolvedOutDir = path.resolve(outDir);
  const jobs: StillJob[] = [];
  let currentFrame = 0;

  for (let idx = 0; idx < scenes.length; idx += 1) {
    const scene = scenes[idx] ?? {};
    const sceneId = scene.id || `scene_${idx}`;
    const durFrames = Math.max(1, Math.trunc(Number(scene.durationInFrames ?? 60)));
    const midFrame = currentFrame + Math.floor(durFrames / 2);
    jobs.push({
      id: sceneId,
      frame: midFrame,
      outputPath: path.join(resolvedOutDir, `${sceneId}_f${midFrame}.${ext}`),
    });
    currentFrame += durFrames;
  }

  return jobs;
}

/**
 * Thực thi mảng công việc với giới hạn số lượng promise song song, bảo toàn thứ tự đầu ra.
 */
export async function runWithConcurrency<T, R>(
  items: T[],
  concurrency: number,
  worker: (item: T, index: number) => Promise<R>
): Promise<R[]> {
  const limit = Math.max(1, Math.min(concurrency, Math.max(1, items.length)));
  const results = new Array<R>(items.length);
  let nextIdx = 0;

  const runners = Array.from({ length: limit }, async () => {
    while (true) {
      const idx = nextIdx;
      nextIdx += 1;
      if (idx >= items.length) {
        break;
      }
      results[idx] = await worker(items[idx], idx);
    }
  });

  await Promise.all(runners);
  return results;
}

export async function flushStdio(): Promise<void> {
  const flushStream = (stream: NodeJS.WriteStream): Promise<void> =>
    new Promise((resolve) => {
      if (stream.destroyed || !stream.writable) {
        resolve();
        return;
      }
      let settled = false;
      const done = () => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          resolve();
        }
      };
      const timer = setTimeout(done, 250);
      timer.unref?.();
      try {
        stream.write("", done);
      } catch {
        done();
      }
    });

  await Promise.all([flushStream(process.stdout), flushStream(process.stderr)]);
}

export async function main(argv: string[] = process.argv.slice(2)): Promise<number> {
  const tAll0 = performance.now();
  const args = parseStillsCliArgs(argv);

  if (!args.propsPath) {
    console.error(
      "Usage: tsx scripts/render_stills.ts --props <render_props.json> (--all-scenes --out-dir <dir> | --frame <n> --out <file> | --jobs <jobs.json>) [--composition StoryComposition] [--concurrency 6] [--gl angle] [--scratch-dir <dir>] [--chapter-id <id>]"
    );
    return 1;
  }

  const resolvedPropsPath = path.resolve(args.propsPath);
  if (!fs.existsSync(resolvedPropsPath)) {
    console.error(`Error: Props file not found at ${resolvedPropsPath}`);
    return 1;
  }

  const inputProps = JSON.parse(fs.readFileSync(resolvedPropsPath, "utf8"));
  const ext = args.imageFormat === "jpeg" ? "jpg" : args.imageFormat;

  const jobs: StillJob[] = [];
  if (args.jobsPath) {
    const rawJobs = JSON.parse(fs.readFileSync(path.resolve(args.jobsPath), "utf8")) as Array<{
      id?: string;
      frame: number;
      outputPath: string;
    }>;
    for (let i = 0; i < rawJobs.length; i += 1) {
      jobs.push({
        id: rawJobs[i].id || `job_${i}`,
        frame: Math.max(0, Math.floor(Number(rawJobs[i].frame))),
        outputPath: path.resolve(rawJobs[i].outputPath),
      });
    }
  } else if (args.allScenes) {
    if (!args.outDir) {
      throw new Error("--all-scenes requires --out-dir <dir>");
    }
    const scenes = Array.isArray(inputProps?.scenes) ? inputProps.scenes : [];
    jobs.push(...buildAllSceneJobs(scenes, args.outDir, ext));
  } else if (args.frame !== undefined && args.outPath) {
    jobs.push({
      id: `frame_${args.frame}`,
      frame: args.frame,
      outputPath: path.resolve(args.outPath),
    });
  } else {
    throw new Error(
      "Must specify either (--all-scenes --out-dir <dir>), (--frame <n> --out <file>), or (--jobs <file>)"
    );
  }

  if (jobs.length === 0) {
    console.log("STILL_SUMMARY count=0/0 bundle_ms=0 select_ms=0 render_ms=0 total_ms=0");
    return 0;
  }

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
    const tBundle0 = performance.now();
    serveUrl = await bundle({
      entryPoint: path.resolve(remotionDir, "src/index.ts"),
      webpackOverride: enableTailwind,
    });
    bundleMs = Math.round(performance.now() - tBundle0);
    console.log("BUNDLE_CACHE hit=0 hash=disabled sync_ms=0 synced_files=0");
  } else {
    const cacheRes = await getOrCreateBundle({
      remotionDir,
      cacheRoot: effectiveScratchDir,
      chapterId,
    });
    serveUrl = cacheRes.serveUrl;
    bundleMs = cacheRes.bundleMs;
    console.log(
      `BUNDLE_CACHE hit=${cacheRes.cacheHit ? 1 : 0} hash=${cacheRes.sourceHash} sync_ms=${cacheRes.syncMs} synced_files=${cacheRes.syncedFiles}`
    );
  }

  // Mở 1 phiên Chromium duy nhất dùng chung cho toàn bộ batch stills
  const browser = await openBrowser("chrome", {
    chromiumOptions: {
      gl: args.gl,
    },
  });

  let selectMs = 0;
  let renderMs = 0;
  let okCount = 0;

  try {
    const tSelect0 = performance.now();
    const composition = await selectComposition({
      serveUrl,
      id: args.compositionId,
      inputProps,
      puppeteerInstance: browser,
    });
    selectMs = Math.round(performance.now() - tSelect0);

    const maxFrame = Math.max(0, composition.durationInFrames - 1);
    const tRender0 = performance.now();

    const statuses = await runWithConcurrency(
      jobs,
      Math.min(args.concurrency, jobs.length),
      async (job) => {
        const clampedFrame = Math.min(Math.max(0, job.frame), maxFrame);
        fs.mkdirSync(path.dirname(job.outputPath), { recursive: true });
        try {
          await renderStill({
            composition,
            serveUrl,
            output: job.outputPath,
            frame: clampedFrame,
            inputProps,
            puppeteerInstance: browser,
            imageFormat: args.imageFormat,
            ...(args.imageFormat === "jpeg" ? { jpegQuality: args.jpegQuality } : {}),
            timeoutInMilliseconds: 120000,
          });
          console.log(`STILL_OK ${job.id} ${clampedFrame} ${job.outputPath}`);
          return true;
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          console.error(`STILL_ERR ${job.id} ${clampedFrame} ${msg}`);
          return false;
        }
      }
    );

    renderMs = Math.round(performance.now() - tRender0);
    okCount = statuses.filter(Boolean).length;
  } finally {
    try {
      await browser.close({ silent: true });
    } catch {
      // Bỏ qua lỗi khi đóng browser để không che khuất ngoại lệ chính
    }
  }

  const totalMs = Math.round(performance.now() - tAll0);
  console.log(
    `STILL_SUMMARY count=${okCount}/${jobs.length} bundle_ms=${bundleMs} select_ms=${selectMs} render_ms=${renderMs} total_ms=${totalMs}`
  );

  return okCount === 0 ? 1 : 0;
}

const isDirectRun =
  typeof process.argv[1] === "string" &&
  path.resolve(process.argv[1]) === path.resolve(__filename);

if (isDirectRun) {
  main()
    .then(async (exitCode) => {
      // Đảm bảo flush sạch stdout/stderr trên Windows pipe trước khi thoát (tránh cắt cụt STILL_SUMMARY)
      await flushStdio();
      process.exit(exitCode);
    })
    .catch(async (err) => {
      console.error("STILL_FATAL:", err);
      await flushStdio();
      process.exit(1);
    });
}
