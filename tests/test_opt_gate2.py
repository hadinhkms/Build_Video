import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.audio.mastering import _encode_final, master_loudness, measure_loudness
from src.core.hardware_profile import detect_hardware_profile
from src.core.scratch_manager import ScratchManager
from src.core.state_manager import StateManager
from src.pipeline.context import PipelineContext
from src.pipeline.stage_video_master import run_stage_video
from src.render.encoder_probe import (
    EncoderCapability,
    clear_encoder_probe_cache,
    probe_encoder_capability,
)
from src.render.remotion_runner import RemotionRunner
from src.video_composer import VideoComposer

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _measure_ebur128(media_path: str):
    res = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            media_path,
            "-vn",
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    i_matches = re.findall(r"I:\s+(-?[\d.]+)\s+LUFS", res.stderr)
    tp_matches = re.findall(r"Peak:\s+(-?[\d.]+)\s+dBFS", res.stderr)
    integrated = float(i_matches[-1]) if i_matches else None
    true_peak = float(tp_matches[-1]) if tp_matches else None
    return integrated, true_peak


def _compute_ffmpeg_ssim(distorted: str, reference: str) -> float:
    res = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            distorted,
            "-i",
            reference,
            "-lavfi",
            "ssim",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    m = re.search(r"All:([0-9.]+)", res.stderr)
    if not m:
        raise AssertionError(f"Không trích xuất được điểm SSIM từ stderr:\n{res.stderr[-400:]}")
    return float(m.group(1))


class TestOptGate2Acceptance(unittest.TestCase):
    """Kiểm thử nghiệm thu OPT Phase 2 (Gate 2): NVENC Bridge, Parallel VideoComposer, SSIM & LUFS."""

    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        clear_encoder_probe_cache()

    def tearDown(self):
        clear_encoder_probe_cache()
        self._tmp.cleanup()

    def test_gate2_1_settings_json_has_all_phase2_keys(self):
        settings_path = self.root / "config" / "settings.json"
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        render = data.get("render", {})
        self.assertIn("encoder", render)
        self.assertIn(render["encoder"], {"auto", "nvenc", "libx264"})
        self.assertIn("nvenc_preset", render)
        self.assertIn("nvenc_cq", render)
        self.assertIn("ffmpeg_workers", render)

    def test_gate2_2_remotion_runner_encoder_flags_and_parser(self):
        runner = RemotionRunner(project_root=self.root)
        cmd = runner.build_command(
            props_path=self.tmp_dir / "props.json",
            output_path=self.tmp_dir / "out.mkv",
            concurrency=16,
            crf=18,
            gl="angle",
            encoder="nvenc",
            nvenc_preset="p5",
            nvenc_cq=19,
            ffmpeg_bin_dir=self.tmp_dir / "ffmpeg_bin",
            supports_bframes=True,
        )
        self.assertIn("--encoder", cmd)
        self.assertEqual(cmd[cmd.index("--encoder") + 1], "nvenc")
        self.assertIn("--nvenc-preset", cmd)
        self.assertEqual(cmd[cmd.index("--nvenc-preset") + 1], "p5")
        self.assertIn("--nvenc-cq", cmd)
        self.assertEqual(cmd[cmd.index("--nvenc-cq") + 1], "19")
        self.assertIn("--ffmpeg-bin-dir", cmd)
        self.assertIn("--nvenc-bframes", cmd)
        self.assertEqual(cmd[cmd.index("--nvenc-bframes") + 1], "1")

        self.assertEqual(
            runner.parse_encoder_active_line("ENCODER_ACTIVE h264_nvenc preset=p5 cq=19 bframes=2"),
            "h264_nvenc",
        )
        self.assertEqual(
            runner.parse_encoder_active_line("ENCODER_ACTIVE libx264 fallback=nvenc_runtime_error"),
            "libx264",
        )
        self.assertIsNone(runner.parse_encoder_active_line("PROGRESS 0.500"))

    def test_gate2_3_mastering_commands_use_threads_0_and_video_stream_copy(self):
        captured = []

        def fake_run(cmd):
            captured.append(cmd)
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="",
                stderr='{"input_i":"-18.0","input_tp":"-3.0","input_lra":"6.0","input_thresh":"-28.0","target_offset":"0.1"}',
            )

        with patch("src.audio.mastering._run", side_effect=fake_run):
            m = measure_loudness("in.mkv", -14.0, -1.5, 11.0)
            self.assertIsNotNone(m)
            _encode_final("in.mkv", "out.mp4", 44100, "loudnorm=I=-14.0")

        self.assertEqual(len(captured), 2)
        for cmd in captured:
            self.assertIn("-threads", cmd)
            self.assertEqual(cmd[cmd.index("-threads") + 1], "0")

        encode_cmd = captured[1]
        self.assertEqual(encode_cmd[encode_cmd.index("-c:v") + 1], "copy")
        self.assertEqual(encode_cmd[encode_cmd.index("-c:a") + 1], "aac")
        self.assertEqual(encode_cmd[encode_cmd.index("-b:a") + 1], "192k")

    def test_gate2_4_stage_video_remotion_respects_nvenc_and_libx264_fallback(self):
        chapter_dir = self.tmp_dir / "output" / "g2_ch"
        audio_dir = chapter_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        (chapter_dir / "render_props.json").write_text(
            json.dumps({"chapterId": "g2_ch", "scenes": [{"durationInFrames": 240}]}),
            encoding="utf-8",
        )
        scratch_dir = self.tmp_dir / "scratch"
        hw = detect_hardware_profile(self.root)
        scratch_mgr = ScratchManager(
            project_root=self.root,
            scratch_dir_setting=str(scratch_dir),
            hardware_profile=hw,
        )

        def make_ctx(enc_mode: str) -> PipelineContext:
            return PipelineContext(
                chapter_file="input/sample_chapter.txt",
                output_name="final_chapter_video.mp4",
                tts_provider="edge",
                renderer="remotion",
                stage="video",
                title=None,
                env=None,
                frames="0-239",
                bench=None,
                settings={
                    "video": {"fps": 24},
                    "render": {
                        "renderer": "remotion",
                        "encoder": enc_mode,
                        "nvenc_preset": "p5",
                        "nvenc_cq": 19,
                        "concurrency": 16,
                        "gl": "angle",
                        "x264_preset": "faster",
                        "crf": 18,
                        "scratch_dir": str(scratch_dir),
                        "bundle_cache": True,
                    },
                },
                story_rules={},
                fps=24,
                shot_min=4.0,
                shot_max=6.5,
                split_min=2.5,
                chapter_id="g2_ch",
                chapter_dir=chapter_dir,
                audio_dir=audio_dir,
                storyboard_path=chapter_dir / "storyboard.json",
                state_mgr=StateManager(str(chapter_dir / "storyboard.json")),
                hardware_profile=hw,
                scratch_manager=scratch_mgr,
            )

        # Trường hợp 1: encoder="auto" -> probe trả h264_nvenc
        nv_cap = EncoderCapability(
            selected_encoder="h264_nvenc",
            requested_encoder="auto",
            nvenc_available=True,
            supports_bframes=True,
            ffmpeg_bin_dir=Path("C:/ffmpeg/bin"),
            max_parallel_nvenc=3,
        )
        seen_nv = {}

        def fake_render_nv(self_r, **kwargs):
            seen_nv.update(kwargs)
            self_r.last_encoder = "h264_nvenc"
            self_r.last_timing = {"bundle_ms": 50, "select_ms": 400, "render_ms": 3000, "encoder": "h264_nvenc"}
            return True

        with patch("src.pipeline.stage_video_master.probe_encoder_capability", return_value=nv_cap), \
             patch.object(RemotionRunner, "render", autospec=True, side_effect=fake_render_nv):
            ok = run_stage_video(make_ctx("auto"))

        self.assertTrue(ok)
        self.assertEqual(seen_nv["encoder"], "nvenc")
        self.assertEqual(seen_nv["nvenc_preset"], "p5")
        self.assertEqual(seen_nv["nvenc_cq"], 19)
        self.assertTrue(seen_nv["supports_bframes"])
        report_nv = json.loads((chapter_dir / "render_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report_nv["encoder"], "h264_nvenc")

        # Trường hợp 2: encoder="libx264" -> ép CPU
        cpu_cap = EncoderCapability(
            selected_encoder="libx264",
            requested_encoder="libx264",
            nvenc_available=False,
            supports_bframes=False,
            ffmpeg_bin_dir=Path("C:/ffmpeg/bin"),
            max_parallel_nvenc=0,
        )
        seen_cpu = {}

        def fake_render_cpu(self_r, **kwargs):
            seen_cpu.update(kwargs)
            self_r.last_encoder = "libx264"
            self_r.last_timing = {"bundle_ms": 50, "select_ms": 400, "render_ms": 5000, "encoder": "libx264"}
            return True

        with patch("src.pipeline.stage_video_master.probe_encoder_capability", return_value=cpu_cap), \
             patch.object(RemotionRunner, "render", autospec=True, side_effect=fake_render_cpu):
            ok_cpu = run_stage_video(make_ctx("libx264"))

        self.assertTrue(ok_cpu)
        self.assertEqual(seen_cpu["encoder"], "libx264")
        self.assertIsNone(seen_cpu["ffmpeg_bin_dir"])
        report_cpu = json.loads((chapter_dir / "render_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report_cpu["encoder"], "libx264")

    @unittest.skipUnless(sys.platform == "win32" and HAS_FFMPEG, "Chỉ chạy cầu nối DLL trên Windows có FFmpeg")
    def test_gate2_5_real_hw_bin_bridge_build_cache_and_dll_collision_simulation(self):
        """Kiểm chứng thực tế dựng hw-bin/, manifest cache hit, và tự hủy khi giả lập va chạm DLL."""
        cap = probe_encoder_capability(requested="auto", force_refresh=True)
        if not cap.is_nvenc or cap.ffmpeg_bin_dir is None:
            self.skipTest("Máy không có h264_nvenc khả dụng")

        npx_cmd = "npx.cmd"
        scratch_path = str(self.tmp_dir / "bridge_scratch")
        sys_ff_dir = str(cap.ffmpeg_bin_dir)
        fake_collision_dir = self.tmp_dir / "colliding_ffmpeg"
        fake_collision_dir.mkdir(parents=True, exist_ok=True)
        (fake_collision_dir / "ffmpeg.exe").write_bytes(b"stub")
        (fake_collision_dir / "ffprobe.exe").write_bytes(b"stub")
        (fake_collision_dir / "AVCODEC-61.DLL").write_bytes(b"collision")

        script = (
            "import fs from 'node:fs'; import path from 'node:path'; "
            "import { findDllCollisions, prepareRemotionNvencBridge, resolveCompositorDir } from './scripts/ffmpeg-bridge'; "
            f"const scratch = {json.dumps(scratch_path)}; "
            f"const sysDir = {json.dumps(sys_ff_dir)}; "
            f"const collideDir = {json.dumps(str(fake_collision_dir))}; "
            "const compDir = resolveCompositorDir(); "
            "const realCollisions = compDir ? findDllCollisions(compDir, sysDir) : ['missing']; "
            "const b1 = prepareRemotionNvencBridge({ scratchDir: scratch, systemFfmpegDir: sysDir, nvencPreset: 'p5', cq: 19, supportsBframes: true }); "
            "const b2 = prepareRemotionNvencBridge({ scratchDir: scratch, systemFfmpegDir: sysDir, nvencPreset: 'p5', cq: 19, supportsBframes: true }); "
            "const hwBin = path.join(scratch, 'hw-bin'); "
            "const anyDll = fs.readdirSync(hwBin).find((f) => f.toLowerCase().endsWith('.dll')); "
            "if (anyDll) fs.unlinkSync(path.join(hwBin, anyDll)); "
            "const b3 = prepareRemotionNvencBridge({ scratchDir: scratch, systemFfmpegDir: sysDir, nvencPreset: 'p5', cq: 19, supportsBframes: true }); "
            "const restored = anyDll ? fs.existsSync(path.join(hwBin, anyDll)) : true; "
            "const bCollide = prepareRemotionNvencBridge({ scratchDir: scratch + '_col', systemFfmpegDir: collideDir }); "
            "console.log(JSON.stringify({ "
            "  realCollisions, "
            "  b1Ok: Boolean(b1), b1Reused: b1?.reusedCache, "
            "  b2Ok: Boolean(b2), b2Reused: b2?.reusedCache, "
            "  b3Ok: Boolean(b3), b3Reused: b3?.reusedCache, restored, "
            "  bCollideNull: bCollide === null "
            "}));"
        )
        res = subprocess.run(
            [npx_cmd, "tsx", "-e", script],
            cwd=str(self.root / "remotion"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            check=True,
        )
        out = json.loads(res.stdout.strip().splitlines()[-1])
        self.assertEqual(out["realCollisions"], [])
        self.assertTrue(out["b1Ok"])
        self.assertFalse(out["b1Reused"])
        self.assertTrue(out["b2Ok"])
        self.assertTrue(out["b2Reused"])
        self.assertTrue(out["b3Ok"])
        self.assertFalse(out["b3Reused"])
        self.assertTrue(out["restored"])
        self.assertTrue(out["bCollideNull"])

    @unittest.skipUnless(HAS_FFMPEG, "Cần ffmpeg/ffprobe")
    def test_gate2_6_nvenc_vs_libx264_ssim_size_and_master_invariants(self):
        """Kiểm chứng thực chiến chất lượng SSIM >= 0.985, tỉ lệ dung lượng <= 1.35x, duration ±1f và -14 LUFS."""
        cap = probe_encoder_capability(requested="auto", force_refresh=True)
        if not cap.is_nvenc:
            self.skipTest("Máy không có h264_nvenc khả dụng")

        img = str(self.tmp_dir / "scene.jpg")
        aud = str(self.tmp_dir / "voice.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=24", "-frames:v", "1", img],
            check=True,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=3.5", "-af", "volume=-20dB", "-ar", "44100", aud],
            check=True,
        )

        nv_clip = str(self.tmp_dir / "nvenc.mov")
        cpu_clip = str(self.tmp_dir / "cpu.mov")

        nv_composer = VideoComposer(
            settings_path=str(self.root / "config" / "settings.json"),
            encoder_capability=cap,
        )
        cpu_cap = probe_encoder_capability(requested="libx264", force_refresh=True)
        cpu_composer = VideoComposer(
            settings_path=str(self.root / "config" / "settings.json"),
            encoder_capability=cpu_cap,
        )
        cpu_composer.x264_preset = "medium"

        self.assertTrue(nv_composer.render_shot_clip(img, aud, nv_clip, "zoom_in", 4.0))
        self.assertTrue(cpu_composer.render_shot_clip(img, aud, cpu_clip, "zoom_in", 4.0))

        ssim = _compute_ffmpeg_ssim(nv_clip, cpu_clip)
        self.assertGreaterEqual(ssim, 0.985, f"SSIM NVENC vs libx264 dưới 0.985: {ssim}")

        nv_size = os.path.getsize(nv_clip)
        cpu_size = os.path.getsize(cpu_clip)
        ratio = nv_size / max(1, cpu_size)
        self.assertLessEqual(ratio, 1.35, f"Tỉ lệ dung lượng NVENC/libx264 vượt 1.35x: {ratio:.2f}x")

        master_out = str(self.tmp_dir / "master.mp4")
        measured = master_loudness(nv_clip, master_out, target_i=-14.0, target_tp=-1.5, target_lra=11.0)
        self.assertIsNotNone(measured)
        dur = VideoComposer.probe_duration(master_out)
        self.assertIsNotNone(dur)
        self.assertAlmostEqual(dur, 4.0, delta=1.0 / 24.0 + 0.01)

        integrated, true_peak = _measure_ebur128(master_out)
        self.assertIsNotNone(integrated)
        self.assertAlmostEqual(integrated, -14.0, delta=1.0)
        if true_peak is not None:
            self.assertLessEqual(true_peak, -1.4)

    def test_gate2_7_benchmark_hardware_forwards_encoder_flags_to_remotion_runner(self):
        """scripts/benchmark_hardware.py phải truyền cờ encoder/nvenc đầy đủ xuống RemotionRunner."""
        from scripts.benchmark_hardware import apply_config_to_settings, run_single_benchmark

        hw = detect_hardware_profile(self.root)
        scratch_mgr = ScratchManager(
            project_root=self.root,
            scratch_dir_setting=str(self.tmp_dir / "bench_scratch"),
            hardware_profile=hw,
        )
        props = self.tmp_dir / "render_props.json"
        props.write_text(json.dumps({"scenes": [{"durationInFrames": 240}]}), encoding="utf-8")

        runner = RemotionRunner(project_root=self.root)
        captured = {}

        def fake_render(self_r, **kwargs):
            captured.update(kwargs)
            self_r.last_encoder = "h264_nvenc"
            self_r.last_timing = {"bundle_ms": 60, "select_ms": 300, "render_ms": 4000, "cache_hit": True, "encoder": "h264_nvenc"}
            return True

        with patch.object(RemotionRunner, "render", autospec=True, side_effect=fake_render):
            res = run_single_benchmark(
                runner=runner,
                scratch_mgr=scratch_mgr,
                hw=hw,
                props_path=props,
                chapter_id="sample_chapter",
                frames_spec="0-239",
                frame_count=240,
                gl="angle",
                concurrency=16,
                x264_preset="veryfast",
                crf=18,
                image_format="jpeg",
                jpeg_quality=85,
                phase_label="sweep_angle",
                max_vram_mb=3400.0,
                max_ram_gb=48.0,
                encoder="nvenc",
                nvenc_preset="p5",
                nvenc_cq=24,
                ffmpeg_bin_dir=Path("C:/ffmpeg/bin"),
                supports_bframes=True,
            )

        self.assertTrue(res["success"])
        self.assertEqual(res["encoder"], "h264_nvenc")
        self.assertEqual(res["nvenc_preset"], "p5")
        self.assertEqual(res["nvenc_cq"], 24)
        self.assertEqual(captured["encoder"], "nvenc")
        self.assertEqual(captured["nvenc_preset"], "p5")
        self.assertEqual(captured["nvenc_cq"], 24)
        self.assertTrue(captured["supports_bframes"])

        fake_settings = self.tmp_dir / "settings_bench.json"
        fake_settings.write_text(json.dumps({"render": {"encoder": "auto", "crf": 18}}), encoding="utf-8")
        updated = apply_config_to_settings(fake_settings, res)
        self.assertEqual(updated["nvenc_preset"], "p5")
        self.assertEqual(updated["nvenc_cq"], 24)
        self.assertEqual(updated["concurrency"], 16)


if __name__ == "__main__":
    unittest.main()
