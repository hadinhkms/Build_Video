import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  buildAllSceneJobs,
  flushStdio,
  main,
  parseStillsCliArgs,
  runWithConcurrency,
} from "../scripts/render_stills";

function collectTsxFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      collectTsxFiles(full, out);
    } else if (entry.isFile() && entry.name.endsWith(".tsx")) {
      out.push(full);
    }
  }
  return out;
}

describe("render_stills & OPT Phase 3 invariants", () => {
  it("parseStillsCliArgs parses --all-scenes and single --frame modes cleanly", () => {
    const batch = parseStillsCliArgs([
      "--props",
      "output/sample_chapter/render_props.json",
      "--all-scenes",
      "--out-dir",
      "output/sample_chapter/stills",
      "--concurrency",
      "6",
      "--gl",
      "angle",
      "--scratch-dir",
      "C:/scratch",
      "--chapter-id",
      "sample_chapter",
    ]);
    expect(batch.allScenes).toBe(true);
    expect(batch.outDir).toBe("output/sample_chapter/stills");
    expect(batch.concurrency).toBe(6);
    expect(batch.gl).toBe("angle");
    expect(batch.chapterId).toBe("sample_chapter");

    const single = parseStillsCliArgs([
      "--props=props.json",
      "--frame=30",
      "--out=thumb.png",
      "--image-format=png",
    ]);
    expect(single.allScenes).toBe(false);
    expect(single.frame).toBe(30);
    expect(single.outPath).toBe("thumb.png");
    expect(single.imageFormat).toBe("png");
  });

  it("buildAllSceneJobs computes exact mid-frame offsets and legacy filenames", () => {
    const jobs = buildAllSceneJobs(
      [
        { id: "shot_00a", durationInFrames: 117 },
        { id: "shot_00b", durationInFrames: 96 },
        { id: "title_card", durationInFrames: 60 },
      ],
      "out/stills"
    );

    expect(jobs.map((j) => j.id)).toEqual(["shot_00a", "shot_00b", "title_card"]);
    expect(jobs.map((j) => j.frame)).toEqual([58, 165, 243]);
    expect(jobs.map((j) => path.basename(j.outputPath))).toEqual([
      "shot_00a_f58.png",
      "shot_00b_f165.png",
      "title_card_f243.png",
    ]);
  });

  it("runWithConcurrency enforces concurrency cap and preserves exact output order", async () => {
    let active = 0;
    let peak = 0;
    const items = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];

    const out = await runWithConcurrency(items, 4, async (val) => {
      active += 1;
      peak = Math.max(peak, active);
      await new Promise((r) => setTimeout(r, (10 - val) * 3));
      active -= 1;
      return val * 10;
    });

    expect(peak).toBeLessThanOrEqual(4);
    expect(peak).toBeGreaterThanOrEqual(2);
    expect(out).toEqual([0, 10, 20, 30, 40, 50, 60, 70, 80, 90]);
  });

  it("remotion/src TSX tree has zero backdrop-filter, blur-[, or drop-shadow classes", () => {
    const srcDir = path.resolve(__dirname, "..", "src");
    const tsxFiles = collectTsxFiles(srcDir);
    expect(tsxFiles.length).toBeGreaterThan(0);

    const forbidden = [
      "backdrop-blur",
      "backdrop-brightness",
      "backdrop-filter",
      "blur-[",
      "drop-shadow",
    ];
    for (const file of tsxFiles) {
      const content = fs.readFileSync(file, "utf8");
      for (const pat of forbidden) {
        expect(content, `${path.basename(file)} must not contain ${pat}`).not.toContain(pat);
      }
    }
  });

  it("flushStdio resolves cleanly and main returns exit code 1 on missing props without hard-exiting", async () => {
    await expect(flushStdio()).resolves.toBeUndefined();
    const exitCode = await main(["--props", path.join(__dirname, "__nonexistent_props__.json")]);
    expect(exitCode).toBe(1);

    const scriptSrc = fs.readFileSync(
      path.resolve(__dirname, "..", "scripts", "render_stills.ts"),
      "utf8"
    );
    expect(scriptSrc).toContain("finally {");
    expect(scriptSrc).toContain("browser.close({ silent: true })");
    expect(scriptSrc).toContain("await flushStdio();");
  });
});
