import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { bundle } from "@remotion/bundler";
import { enableTailwind } from "@remotion/tailwind-v4";

export interface BundleCacheOptions {
  remotionDir: string;
  cacheRoot: string;
  chapterId?: string | null;
  forceRebuild?: boolean;
}

export interface BundleCacheResult {
  serveUrl: string;
  sourceHash: string;
  cacheHit: boolean;
  bundleMs: number;
  syncMs: number;
  syncedFiles: number;
}

const ROOT_CONFIG_FILES = [
  "package.json",
  "package-lock.json",
  "tsconfig.json",
  "remotion.config.ts",
];

function collectFilesRecursively(dir: string, baseDir: string, out: string[]): void {
  if (!fs.existsSync(dir)) {
    return;
  }
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  entries.sort((a, b) => a.name.localeCompare(b.name));
  for (const entry of entries) {
    if (entry.name === ".DS_Store" || entry.name === "Thumbs.db") {
      continue;
    }
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      collectFilesRecursively(fullPath, baseDir, out);
    } else if (entry.isFile()) {
      const rel = path.relative(baseDir, fullPath).split(path.sep).join("/");
      out.push(rel);
    }
  }
}

/**
 * Tính SHA-256 (16 ký tự hex) của toàn bộ mã nguồn Remotion và các tệp cấu hình build.
 */
export function computeSourceHash(remotionDir: string): string {
  const resolvedRoot = path.resolve(remotionDir);
  const relFiles: string[] = [];

  collectFilesRecursively(path.join(resolvedRoot, "src"), resolvedRoot, relFiles);

  for (const cfg of ROOT_CONFIG_FILES) {
    const fullCfg = path.join(resolvedRoot, cfg);
    if (fs.existsSync(fullCfg) && fs.statSync(fullCfg).isFile()) {
      relFiles.push(cfg);
    }
  }

  relFiles.sort();

  const hasher = crypto.createHash("sha256");
  for (const rel of relFiles) {
    const absPath = path.join(resolvedRoot, rel);
    hasher.update(rel);
    hasher.update("\0");
    hasher.update(fs.readFileSync(absPath));
    hasher.update("\0");
  }
  return hasher.digest("hex").slice(0, 16);
}

/**
 * Đồng bộ gia tăng từ srcDir sang dstDir (chỉ copy khi thiếu hoặc khác size/mtime),
 * đồng thời dọn file thừa đã bị xóa ở nguồn để không bao giờ phục vụ asset cũ.
 */
export function syncDirectoryIncremental(srcDir: string, dstDir: string): number {
  if (!fs.existsSync(srcDir)) {
    return 0;
  }

  fs.mkdirSync(dstDir, { recursive: true });
  let copiedCount = 0;

  const srcEntries = fs
    .readdirSync(srcDir, { withFileTypes: true })
    .filter((e) => e.name !== ".DS_Store" && e.name !== "Thumbs.db" && e.name !== ".asset_opt_cache.json");
  const srcNames = new Set(srcEntries.map((e) => e.name));

  // Xóa file/thư mục cũ không còn ở nguồn
  if (fs.existsSync(dstDir)) {
    for (const dstEntry of fs.readdirSync(dstDir, { withFileTypes: true })) {
      if (!srcNames.has(dstEntry.name)) {
        fs.rmSync(path.join(dstDir, dstEntry.name), { recursive: true, force: true });
      }
    }
  }

  for (const entry of srcEntries) {
    const srcPath = path.join(srcDir, entry.name);
    const dstPath = path.join(dstDir, entry.name);

    if (entry.isDirectory()) {
      if (fs.existsSync(dstPath) && !fs.statSync(dstPath).isDirectory()) {
        fs.rmSync(dstPath, { force: true });
      }
      copiedCount += syncDirectoryIncremental(srcPath, dstPath);
    } else if (entry.isFile()) {
      const srcStat = fs.statSync(srcPath);
      let needsCopy = true;
      if (fs.existsSync(dstPath)) {
        const dstStat = fs.statSync(dstPath);
        if (dstStat.isDirectory()) {
          fs.rmSync(dstPath, { recursive: true, force: true });
        } else if (
          dstStat.isFile() &&
          dstStat.size === srcStat.size &&
          Math.abs(dstStat.mtimeMs - srcStat.mtimeMs) <= 1.0
        ) {
          needsCopy = false;
        }
      }
      if (needsCopy) {
        fs.copyFileSync(srcPath, dstPath);
        try {
          fs.utimesSync(dstPath, srcStat.atime, srcStat.mtime);
        } catch {
          // Bỏ qua nếu hệ thống tệp không cho đặt lại mtime
        }
        copiedCount += 1;
      }
    }
  }

  return copiedCount;
}

/**
 * Giữ tối đa `maxKeep` thư mục hash mới nhất trong bundle-cache, xóa các bản cũ hơn.
 */
export function pruneOldBundles(bundleCacheDir: string, keepHash: string, maxKeep = 2): void {
  if (!fs.existsSync(bundleCacheDir)) {
    return;
  }
  const entries = fs
    .readdirSync(bundleCacheDir, { withFileTypes: true })
    .filter((e) => e.isDirectory() && !e.name.startsWith(".") && e.name !== keepHash);

  const ranked = entries.map((e) => {
    const dirPath = path.join(bundleCacheDir, e.name);
    const markerPath = path.join(dirPath, ".bundle-complete");
    let mtimeMs = 0;
    try {
      mtimeMs = fs.existsSync(markerPath)
        ? fs.statSync(markerPath).mtimeMs
        : fs.statSync(dirPath).mtimeMs;
    } catch {
      mtimeMs = 0;
    }
    return { name: e.name, dirPath, mtimeMs };
  });

  ranked.sort((a, b) => b.mtimeMs - a.mtimeMs);

  const allowedOthers = Math.max(0, maxKeep - 1);
  for (const old of ranked.slice(allowedOthers)) {
    try {
      fs.rmSync(old.dirPath, { recursive: true, force: true });
    } catch {
      // Không để lỗi dọn cache làm hỏng render
    }
  }
}

/**
 * Lấy Webpack bundle đã cache trên NVMe theo SHA-256 mã nguồn, hoặc biên dịch mới khi cache miss.
 * Luôn đồng bộ gia tăng textures/ và chapters/<chapterId>/ vào <targetDir>/public/.
 */
export async function getOrCreateBundle({
  remotionDir,
  cacheRoot,
  chapterId = null,
  forceRebuild = false,
}: BundleCacheOptions): Promise<BundleCacheResult> {
  const t0 = performance.now();
  const resolvedRemotionDir = path.resolve(remotionDir);
  const resolvedCacheRoot = path.resolve(cacheRoot);

  const sourceHash = computeSourceHash(resolvedRemotionDir);
  const bundleCacheDir = path.join(resolvedCacheRoot, "bundle-cache");
  const targetDir = path.join(bundleCacheDir, sourceHash);
  const indexHtmlPath = path.join(targetDir, "index.html");
  const markerPath = path.join(targetDir, ".bundle-complete");

  const cacheHit =
    !forceRebuild && fs.existsSync(indexHtmlPath) && fs.existsSync(markerPath);

  if (cacheHit) {
    try {
      const now = new Date();
      fs.utimesSync(markerPath, now, now);
    } catch {
      // Bỏ qua lỗi chạm mtime
    }
  } else {
    if (fs.existsSync(targetDir)) {
      fs.rmSync(targetDir, { recursive: true, force: true });
    }
    fs.mkdirSync(targetDir, { recursive: true });

    // @remotion/bundler@4.0.407 treats `publicDir: null` as falsy and falls back to copying
    // the entire `remotion/public/` tree (all chapters on slow USB HDD). Pass a dedicated
    // empty directory so bundle() writes `/public` metadata without copying unrelated chapters.
    const emptyPublicDir = path.join(bundleCacheDir, ".empty-public");
    if (fs.existsSync(emptyPublicDir)) {
      fs.rmSync(emptyPublicDir, { recursive: true, force: true });
    }
    fs.mkdirSync(emptyPublicDir, { recursive: true });

    await bundle({
      entryPoint: path.resolve(resolvedRemotionDir, "src/index.ts"),
      webpackOverride: enableTailwind,
      outDir: targetDir,
      enableCaching: true,
      publicDir: emptyPublicDir,
    });

    fs.writeFileSync(
      markerPath,
      JSON.stringify(
        {
          sourceHash,
          createdAt: new Date().toISOString(),
        },
        null,
        2
      ),
      "utf8"
    );

    pruneOldBundles(bundleCacheDir, sourceHash, 2);
  }

  // Đồng bộ gia tăng public/textures và public/chapters/<chapterId> sang NVMe
  const tSync0 = performance.now();
  const srcPublic = path.join(resolvedRemotionDir, "public");
  const dstPublic = path.join(targetDir, "public");
  let syncedFiles = 0;

  syncedFiles += syncDirectoryIncremental(
    path.join(srcPublic, "textures"),
    path.join(dstPublic, "textures")
  );

  if (chapterId) {
    syncedFiles += syncDirectoryIncremental(
      path.join(srcPublic, "chapters", chapterId),
      path.join(dstPublic, "chapters", chapterId)
    );
  } else {
    syncedFiles += syncDirectoryIncremental(
      path.join(srcPublic, "chapters"),
      path.join(dstPublic, "chapters")
    );
  }

  const syncMs = Math.round(performance.now() - tSync0);
  const bundleMs = Math.round(performance.now() - t0);

  return {
    serveUrl: targetDir,
    sourceHash,
    cacheHit,
    bundleMs,
    syncMs,
    syncedFiles,
  };
}
