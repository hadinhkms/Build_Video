import fs from "node:fs";
import path from "node:path";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import { enableTailwind } from "@remotion/tailwind-v4";

async function main() {
  const [propsPath, outPath, concurrencyArg, crfArg] = process.argv.slice(2);
  if (!propsPath || !outPath) {
    console.error("Usage: tsx scripts/render.ts <propsPath> <outPath> [concurrency|auto] [crf]");
    process.exit(1);
  }

  const resolvedPropsPath = path.resolve(propsPath);
  const resolvedOutPath = path.resolve(outPath);

  if (!fs.existsSync(resolvedPropsPath)) {
    console.error(`Error: Props file not found at ${resolvedPropsPath}`);
    process.exit(1);
  }

  const rawProps = fs.readFileSync(resolvedPropsPath, "utf8");
  const inputProps = JSON.parse(rawProps);

  const concurrency =
    concurrencyArg === undefined ||
    concurrencyArg === "auto" ||
    concurrencyArg === "null" ||
    concurrencyArg === ""
      ? null
      : Number(concurrencyArg);

  const crf = crfArg ? Number(crfArg) : 18;

  // bundle() không đọc remotion.config.ts -> phải tự truyền Tailwind
  console.log("Bundling Remotion project with Tailwind v4...");
  const serveUrl = await bundle({
    entryPoint: path.resolve("src/index.ts"),
    webpackOverride: enableTailwind,
  });

  console.log("Selecting composition 'StoryComposition'...");
  const composition = await selectComposition({
    serveUrl,
    id: "StoryComposition",
    inputProps,
  });

  console.log(
    `Rendering media: ${composition.width}x${composition.height} @ ${composition.fps}fps, ${composition.durationInFrames} frames (concurrency=${concurrency ?? "auto"}, crf=${crf})...`
  );

  fs.mkdirSync(path.dirname(resolvedOutPath), { recursive: true });

  await renderMedia({
    composition,
    serveUrl,
    inputProps,
    codec: "h264-mkv", // Video H.264 + Audio PCM 16-bit
    crf,
    pixelFormat: "yuv420p",
    concurrency,
    timeoutInMilliseconds: 120000,
    chromiumOptions: {
      gl: "angle",
    },
    outputLocation: resolvedOutPath,
    onProgress: ({ progress }) => {
      console.log(`PROGRESS ${progress.toFixed(3)}`);
    },
  });

  console.log(`RENDER_COMPLETE ${resolvedOutPath}`);
}

main().catch((err) => {
  console.error("RENDER_ERROR:", err);
  process.exit(1);
});
