import childProcess from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import type { FfmpegOverrideFn } from "@remotion/renderer";

export interface NvencOverrideOptions {
  nvencPreset?: string;
  cq?: number;
  supportsBframes?: boolean;
}

export interface NvencBridgeOptions {
  scratchDir: string;
  systemFfmpegDir: string;
  nvencPreset?: string;
  cq?: number;
  supportsBframes?: boolean;
  compositorDirOverride?: string;
}

export interface NvencBridgeResult {
  binariesDirectory: string;
  ffmpegOverride: FfmpegOverrideFn;
  compositorDir: string;
  systemFfmpegDir: string;
  reusedCache: boolean;
  nvencPreset: string;
  cq: number;
  supportsBframes: boolean;
}

interface ManifestFileSig {
  name: string;
  size: number;
  mtimeMs: number;
}

const VALID_NVENC_PRESETS = new Set(["p1", "p2", "p3", "p4", "p5", "p6", "p7"]);
const MANIFEST_FILENAME = ".hw-bin-manifest.json";

/**
 * Tìm thư mục chứa ffmpeg.exe trên PATH hệ thống (dùng khi render.ts chạy độc lập).
 */
export function findSystemFfmpegDir(): string | null {
  const pathEnv = process.env.PATH || process.env.Path || "";
  const exeName = process.platform === "win32" ? "ffmpeg.exe" : "ffmpeg";
  for (const rawDir of pathEnv.split(path.delimiter)) {
    const dir = rawDir.trim().replace(/^"|"$/g, "");
    if (!dir) continue;
    const candidate = path.join(dir, exeName);
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      return path.resolve(dir);
    }
  }
  return null;
}

/**
 * Lấy đường dẫn thư mục @remotion/compositor-win32-x64-msvc của Remotion.
 */
export function resolveCompositorDir(): string | null {
  if (process.platform !== "win32" || process.arch !== "x64") {
    return null;
  }
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const pkg = require("@remotion/compositor-win32-x64-msvc") as { dir?: string };
    if (pkg && typeof pkg.dir === "string" && fs.existsSync(pkg.dir)) {
      return path.resolve(pkg.dir);
    }
  } catch {
    return null;
  }
  return null;
}

function listDllNames(dir: string): string[] {
  if (!fs.existsSync(dir)) {
    return [];
  }
  return fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".dll"))
    .map((entry) => entry.name)
    .sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
}

/**
 * Kiểm tra va chạm tệp *.dll (không phân biệt hoa thường) giữa 2 thư mục.
 * Trả về danh sách tên DLL trùng nhau (rỗng nếu an toàn để ghép vào hw-bin/).
 */
export function findDllCollisions(compositorDir: string, systemFfmpegDir: string): string[] {
  const compDlls = listDllNames(compositorDir);
  const sysDlls = listDllNames(systemFfmpegDir);
  const compLower = new Map<string, string>();
  for (const name of compDlls) {
    compLower.set(name.toLowerCase(), name);
  }
  const collisions: string[] = [];
  for (const name of sysDlls) {
    const key = name.toLowerCase();
    if (compLower.has(key)) {
      collisions.push(name);
    }
  }
  return collisions.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
}

function collectFileSigs(dir: string, fileNames: string[]): ManifestFileSig[] {
  return fileNames
    .map((name) => {
      const st = fs.statSync(path.join(dir, name));
      return {
        name,
        size: st.size,
        mtimeMs: Math.round(st.mtimeMs),
      };
    })
    .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
}

function computeManifestFingerprint(
  compositorDir: string,
  compositorFiles: ManifestFileSig[],
  systemFfmpegDir: string,
  systemFiles: ManifestFileSig[]
): string {
  const payload = JSON.stringify({
    compositorDir: path.resolve(compositorDir).toLowerCase(),
    compositorFiles,
    systemFfmpegDir: path.resolve(systemFfmpegDir).toLowerCase(),
    systemFiles,
  });
  return crypto.createHash("sha256").update(payload).digest("hex").slice(0, 24);
}

/**
 * Tự kiểm chứng remotion.exe, ffmpeg.exe (có h264_nvenc) và ffprobe.exe trong hw-bin/.
 */
export function verifyHwBinDirectory(hwBinDir: string): { ok: boolean; reason?: string } {
  const remotionExe = path.join(hwBinDir, "remotion.exe");
  const ffmpegExe = path.join(hwBinDir, "ffmpeg.exe");
  const ffprobeExe = path.join(hwBinDir, "ffprobe.exe");

  if (!fs.existsSync(remotionExe) || !fs.existsSync(ffmpegExe) || !fs.existsSync(ffprobeExe)) {
    return { ok: false, reason: "missing_executables" };
  }

  // 1. Kiểm chứng remotion.exe nạp DLL thành công (không văng NTSTATUS DLL missing/entrypoint)
  const remRes = childProcess.spawnSync(remotionExe, ["--version"], {
    cwd: hwBinDir,
    encoding: "utf8",
    timeout: 20000,
    windowsHide: true,
  });
  const remCombined = `${remRes.stdout ?? ""}\n${remRes.stderr ?? ""}`;
  const remLoaded =
    !remRes.error &&
    (remRes.status === 0 ||
      (remRes.status === 1 &&
        (remCombined.includes("remotion::") || remCombined.includes('"error"'))));
  if (!remLoaded) {
    return {
      ok: false,
      reason: `remotion_exe_check_failed(status=${remRes.status},err=${remRes.error?.message ?? "none"})`,
    };
  }

  // 2. Kiểm chứng ffmpeg.exe nhận diện h264_nvenc (timeout 20s phòng Windows Defender quét lần đầu copy DLL lớn)
  const ffRes = childProcess.spawnSync(
    ffmpegExe,
    ["-hide_banner", "-h", "encoder=h264_nvenc"],
    {
      cwd: hwBinDir,
      encoding: "utf8",
      timeout: 20000,
      windowsHide: true,
    }
  );
  const ffOut = `${ffRes.stdout ?? ""}\n${ffRes.stderr ?? ""}`;
  if (ffRes.error || ffRes.status !== 0 || !ffOut.includes("h264_nvenc")) {
    return {
      ok: false,
      reason: `ffmpeg_nvenc_check_failed(status=${ffRes.status},err=${ffRes.error?.message ?? "none"})`,
    };
  }

  // 3. Kiểm chứng ffprobe.exe chạy sạch
  const fpRes = childProcess.spawnSync(ffprobeExe, ["-version"], {
    cwd: hwBinDir,
    encoding: "utf8",
    timeout: 20000,
    windowsHide: true,
  });
  if (fpRes.error || fpRes.status !== 0) {
    return {
      ok: false,
      reason: `ffprobe_check_failed(status=${fpRes.status},err=${fpRes.error?.message ?? "none"})`,
    };
  }

  return { ok: true };
}

/**
 * Xây dựng hàm ffmpegOverride cho renderMedia().
 * CHỈ viết lại khi args mã hóa bằng libx264; tuyệt đối giữ nguyên khi -c:v copy (bước stitcher).
 */
export function buildNvencOverride(options: NvencOverrideOptions = {}): FfmpegOverrideFn {
  const nvencPreset =
    options.nvencPreset && VALID_NVENC_PRESETS.has(options.nvencPreset)
      ? options.nvencPreset
      : "p5";
  const cq =
    typeof options.cq === "number" && Number.isFinite(options.cq)
      ? Math.max(1, Math.min(51, Math.round(options.cq)))
      : 19;
  const supportsBframes = options.supportsBframes !== false;

  const nvencArgs: string[] = [
    "-c:v",
    "h264_nvenc",
    "-preset",
    nvencPreset,
    "-tune",
    "hq",
    "-rc",
    "vbr",
    "-cq",
    String(cq),
    "-b:v",
    "0",
    "-spatial-aq",
    "1",
    "-aq-strength",
    "8",
    "-bf",
    supportsBframes ? "2" : "0",
  ];

  return ({ args }) => {
    const strArgs = args.map((item) => String(item));

    // Chỉ chuyển đổi khi thực sự có cặp video encoder là libx264 (bỏ qua -c:v copy ở bước stitcher)
    const isVideoCodecFlag = (f: string): boolean =>
      f === "-c:v" || f === "-vcodec" || f === "-codec:v" || f === "-codec:video" || f === "-c:v:0";

    let codecFlagIdx = -1;
    for (let i = 0; i < strArgs.length - 1; i += 1) {
      if (isVideoCodecFlag(strArgs[i]) && strArgs[i + 1] === "libx264") {
        codecFlagIdx = i;
        break;
      }
    }

    if (codecFlagIdx === -1) {
      return args;
    }

    const rewritten: string[] = [];
    let inserted = false;

    for (let i = 0; i < strArgs.length; i += 1) {
      const token = strArgs[i];
      const next = i + 1 < strArgs.length ? strArgs[i + 1] : undefined;

      if (isVideoCodecFlag(token) && next === "libx264") {
        if (!inserted) {
          rewritten.push(...nvencArgs);
          inserted = true;
        }
        i += 1;
        continue;
      }

      if (
        (token === "-crf" ||
          token === "-preset" ||
          token === "-preset:v" ||
          token === "-x264-params" ||
          token === "-x264opts") &&
        next !== undefined
      ) {
        i += 1;
        continue;
      }

      rewritten.push(token);
    }

    return rewritten;
  };
}

/**
 * Nhận diện lỗi runtime liên quan đến NVENC/FFmpeg để render.ts tự retry 1 lần về libx264.
 */
export function isNvencRuntimeError(err: unknown): boolean {
  const msg = err instanceof Error ? `${err.message}\n${err.stack ?? ""}` : String(err ?? "");
  const lower = msg.toLowerCase();
  const patterns = [
    "openencodesessionex",
    "cannot load nvcuda",
    "h264_nvenc",
    "nvenc",
    "no capable devices found",
    "incompatible client key",
    "cuda_error",
    "out of memory",
    "ffmpeg exited with code",
    "error while opening encoder",
    "failed locking bitstream buffer",
  ];
  return patterns.some((p) => lower.includes(p));
}

/**
 * Dựng cầu nối <scratchDir>/hw-bin/ an toàn DLL ghép remotion.exe với ffmpeg.exe hệ thống có NVENC.
 * Trả về `null` nếu có bất kỳ va chạm DLL hoặc tự kiểm chứng thất bại (fallback êm về libx264).
 */
export function prepareRemotionNvencBridge(
  opts: NvencBridgeOptions
): NvencBridgeResult | null {
  if (process.platform !== "win32") {
    console.warn("NVENC_BRIDGE_DISABLED reason=unsupported_platform");
    return null;
  }

  const compositorDir = opts.compositorDirOverride
    ? path.resolve(opts.compositorDirOverride)
    : resolveCompositorDir();
  if (!compositorDir || !fs.existsSync(compositorDir)) {
    console.warn("NVENC_BRIDGE_DISABLED reason=compositor_dir_missing");
    return null;
  }

  const systemFfmpegDir = path.resolve(opts.systemFfmpegDir);
  if (!fs.existsSync(systemFfmpegDir)) {
    console.warn(`NVENC_BRIDGE_DISABLED reason=system_ffmpeg_dir_missing dir=${systemFfmpegDir}`);
    return null;
  }

  const compRemotionExe = path.join(compositorDir, "remotion.exe");
  const sysFfmpegExe = path.join(systemFfmpegDir, "ffmpeg.exe");
  const sysFfprobeExe = path.join(systemFfmpegDir, "ffprobe.exe");

  if (!fs.existsSync(compRemotionExe)) {
    console.warn(`NVENC_BRIDGE_DISABLED reason=remotion_exe_missing dir=${compositorDir}`);
    return null;
  }
  if (!fs.existsSync(sysFfmpegExe) || !fs.existsSync(sysFfprobeExe)) {
    console.warn(`NVENC_BRIDGE_DISABLED reason=system_ffmpeg_missing dir=${systemFfmpegDir}`);
    return null;
  }

  // 1. Kiểm tra va chạm *.dll động (không phân biệt hoa thường)
  const collisions = findDllCollisions(compositorDir, systemFfmpegDir);
  if (collisions.length > 0) {
    console.warn(
      `NVENC_BRIDGE_DISABLED reason=dll_collision files=${collisions.join(",")}`
    );
    return null;
  }

  const compDlls = listDllNames(compositorDir);
  const sysDlls = listDllNames(systemFfmpegDir);
  const compCopyList = ["remotion.exe", ...compDlls];
  const sysCopyList = ["ffmpeg.exe", "ffprobe.exe", ...sysDlls];

  const compSigs = collectFileSigs(compositorDir, compCopyList);
  const sysSigs = collectFileSigs(systemFfmpegDir, sysCopyList);
  const fingerprint = computeManifestFingerprint(
    compositorDir,
    compSigs,
    systemFfmpegDir,
    sysSigs
  );

  const hwBinDir = path.join(path.resolve(opts.scratchDir), "hw-bin");
  const manifestPath = path.join(hwBinDir, MANIFEST_FILENAME);
  const allExpectedSigs = [...compSigs, ...sysSigs];
  let reusedCache = false;

  if (fs.existsSync(manifestPath)) {
    try {
      const existing = JSON.parse(fs.readFileSync(manifestPath, "utf8")) as {
        fingerprint?: string;
      };
      if (existing.fingerprint === fingerprint) {
        const allPresentWithExpectedSize = allExpectedSigs.every((sig) => {
          const dstPath = path.join(hwBinDir, sig.name);
          if (!fs.existsSync(dstPath)) return false;
          const st = fs.statSync(dstPath);
          return st.isFile() && st.size === sig.size;
        });
        if (allPresentWithExpectedSize) {
          reusedCache = true;
        }
      }
    } catch {
      reusedCache = false;
    }
  }

  const populateHwBin = (forceOverwrite: boolean): boolean => {
    try {
      fs.mkdirSync(hwBinDir, { recursive: true });
      const expectedFiles = new Set(
        [...compCopyList, ...sysCopyList, MANIFEST_FILENAME].map((f) => f.toLowerCase())
      );

      // Dọn tệp cũ không còn trong danh sách ghép
      for (const entry of fs.readdirSync(hwBinDir, { withFileTypes: true })) {
        if (!expectedFiles.has(entry.name.toLowerCase())) {
          fs.rmSync(path.join(hwBinDir, entry.name), { recursive: true, force: true });
        }
      }

      const copyIfChanged = (srcDir: string, fileName: string): void => {
        const srcPath = path.join(srcDir, fileName);
        const dstPath = path.join(hwBinDir, fileName);
        const srcStat = fs.statSync(srcPath);
        if (!forceOverwrite && fs.existsSync(dstPath)) {
          const dstStat = fs.statSync(dstPath);
          if (
            dstStat.isFile() &&
            dstStat.size === srcStat.size &&
            Math.abs(dstStat.mtimeMs - srcStat.mtimeMs) <= 1.0
          ) {
            return;
          }
        }
        fs.copyFileSync(srcPath, dstPath);
        try {
          fs.utimesSync(dstPath, srcStat.atime, srcStat.mtime);
        } catch {
          // Bỏ qua nếu không đặt lại được mtime
        }
      };

      for (const f of compCopyList) {
        copyIfChanged(compositorDir, f);
      }
      for (const f of sysCopyList) {
        copyIfChanged(systemFfmpegDir, f);
      }

      fs.writeFileSync(
        manifestPath,
        JSON.stringify(
          {
            fingerprint,
            createdAt: new Date().toISOString(),
            compositorDir,
            systemFfmpegDir,
            compositorFileCount: compCopyList.length,
            systemFileCount: sysCopyList.length,
          },
          null,
          2
        ),
        "utf8"
      );
      return true;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.warn(`NVENC_BRIDGE_DISABLED reason=copy_failed detail=${msg}`);
      return false;
    }
  };

  if (!reusedCache) {
    if (!populateHwBin(false)) {
      return null;
    }
  }

  // 2. Tự kiểm chứng nhanh remotion.exe + ffmpeg.exe (h264_nvenc) + ffprobe.exe
  let check = verifyHwBinDirectory(hwBinDir);
  if (!check.ok && reusedCache) {
    // Tự phục hồi 1 lần nếu tệp trong cache hw-bin/ bị hỏng ngầm dù manifest khớp
    console.warn(
      `NVENC_BRIDGE_CACHE_REPAIR reason=${check.reason} action=rebuild_hw_bin`
    );
    reusedCache = false;
    if (!populateHwBin(true)) {
      return null;
    }
    check = verifyHwBinDirectory(hwBinDir);
  }
  if (!check.ok) {
    console.warn(`NVENC_BRIDGE_DISABLED reason=${check.reason}`);
    return null;
  }

  const nvencPreset =
    opts.nvencPreset && VALID_NVENC_PRESETS.has(opts.nvencPreset)
      ? opts.nvencPreset
      : "p5";
  const cq =
    typeof opts.cq === "number" && Number.isFinite(opts.cq)
      ? Math.max(1, Math.min(51, Math.round(opts.cq)))
      : 19;
  const supportsBframes = opts.supportsBframes !== false;

  return {
    binariesDirectory: hwBinDir,
    ffmpegOverride: buildNvencOverride({ nvencPreset, cq, supportsBframes }),
    compositorDir,
    systemFfmpegDir,
    reusedCache,
    nvencPreset,
    cq,
    supportsBframes,
  };
}
