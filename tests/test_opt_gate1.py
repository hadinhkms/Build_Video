import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.benchmark_hardware import apply_config_to_settings, select_best_config
from src.core.hardware_profile import detect_hardware_profile
from src.core.scratch_manager import ScratchManager
from src.core.state_manager import StateManager
from src.pipeline.context import PipelineContext
from src.pipeline.runner import execute_pipeline
from src.pipeline.stage_video_master import _find_prenorm_path, run_stage_master, run_stage_video
from src.render.remotion_runner import RemotionRunner


class TestOptGate1Acceptance(unittest.TestCase):
    """Kiểm thử nghiệm thu OPT Phase 1 (Gate 1)."""

    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_context(self, chapter_id: str = "unit_ch", frames=None, bench=None) -> PipelineContext:
        chapter_dir = self.tmp_dir / "output" / chapter_id
        audio_dir = chapter_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        (chapter_dir / "render_props.json").write_text(
            json.dumps({"chapterId": chapter_id, "scenes": [{"durationInFrames": 240}]}),
            encoding="utf-8",
        )
        scratch_dir = self.tmp_dir / "nvme_scratch"
        settings = {
            "video": {"fps": 24},
            "audio": {
                "sample_rate": 44100,
                "loudness": {"integrated_lufs": -14.0, "true_peak_db": -1.5, "lra": 11.0},
            },
            "visuals": {"shot_min_duration": 4.0, "shot_max_duration": 6.5},
            "render": {
                "renderer": "remotion",
                "encoder": "auto",
                "concurrency": 16,
                "gl": "angle",
                "x264_preset": "faster",
                "crf": 18,
                "image_format": "jpeg",
                "jpeg_quality": 85,
                "scratch_dir": str(scratch_dir),
                "bundle_cache": True,
            },
        }
        hw = detect_hardware_profile(self.root)
        scratch_mgr = ScratchManager(
            project_root=self.root,
            scratch_dir_setting=str(scratch_dir),
            hardware_profile=hw,
        )
        return PipelineContext(
            chapter_file="input/sample_chapter.txt",
            output_name="final_chapter_video.mp4",
            tts_provider="edge",
            renderer="remotion",
            stage="video",
            title=None,
            env=None,
            frames=frames,
            bench=bench,
            settings=settings,
            story_rules={},
            fps=24,
            shot_min=4.0,
            shot_max=6.5,
            split_min=2.5,
            chapter_id=chapter_id,
            chapter_dir=chapter_dir,
            audio_dir=audio_dir,
            storyboard_path=chapter_dir / "storyboard.json",
            state_mgr=StateManager(str(chapter_dir / "storyboard.json")),
            hardware_profile=hw,
            scratch_manager=scratch_mgr,
        )

    def test_gate1_1_hardware_profile_and_nvme_scratch_auto_detection(self):
        hw = detect_hardware_profile(self.root, force_refresh=True)
        self.assertGreaterEqual(hw.cpu_physical_cores, 1)
        self.assertGreaterEqual(hw.cpu_logical_threads, hw.cpu_physical_cores)
        self.assertGreater(hw.ram_total_gb, 0.0)

        mgr = ScratchManager(project_root=self.root, scratch_dir_setting="auto", hardware_profile=hw)
        if hw.workspace_disk_type in ("USB", "HDD") and hw.localappdata_disk_type in ("NVMe", "SSD") and hw.localappdata_free_gb >= 15.0:
            self.assertTrue(mgr.using_nvme_offload)
            self.assertIn("CineStory", str(mgr.scratch_root))

    def test_gate1_2_stage_video_writes_prenorm_on_scratch_and_master_promotes_and_cleans(self):
        ctx = self._make_context("gate1_ch")
        expected_prenorm = ctx.scratch_manager.prenorm_mkv_path("gate1_ch")
        captured_kwargs = {}

        def fake_render(self_runner, **kwargs):
            captured_kwargs.update(kwargs)
            out_p = Path(kwargs["output_path"])
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_bytes(b"FAKE_PRENORM_MKV")
            self_runner.last_timing = {
                "bundle_ms": 120,
                "select_ms": 400,
                "render_ms": 4000,
                "cache_hit": True,
            }
            return True

        with patch.object(RemotionRunner, "render", autospec=True, side_effect=fake_render), \
             patch.object(RemotionRunner, "probe_media_streams", return_value={"streams": [{"codec_type": "audio", "codec_name": "pcm_s16le"}]}):
            ok_video = run_stage_video(ctx)

        self.assertTrue(ok_video)
        self.assertEqual(Path(captured_kwargs["output_path"]), expected_prenorm)
        self.assertTrue(expected_prenorm.exists())
        # Không ghi bản prenorm lên chapter_dir
        self.assertFalse((ctx.chapter_dir / "video.prenorm.mkv").exists())
        self.assertEqual(captured_kwargs["gl"], "angle")
        self.assertEqual(captured_kwargs["x264_preset"], "faster")
        self.assertEqual(captured_kwargs["concurrency"], 16)
        self.assertEqual(captured_kwargs["chapter_id"], "gate1_ch")

        # Kiểm tra render_report.json có timing đầy đủ
        report = json.loads((ctx.chapter_dir / "render_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["bundle_ms"], 120)
        self.assertEqual(report["render_ms"], 4000)
        self.assertAlmostEqual(report["fps_render"], 60.0, places=1)

        # Kiểm tra stage master: đọc prenorm trên scratch -> master vào temp -> promote về output -> dọn work/
        def fake_master_loudness(src, dst, **kwargs):
            self.assertEqual(Path(src), expected_prenorm)
            self.assertEqual(Path(dst).parent, ctx.scratch_manager.chapter_work_dir("gate1_ch"))
            Path(dst).write_bytes(b"MASTERED_MP4_DATA")
            return {"input_i": -14.0}

        with patch("src.pipeline.stage_video_master.master_loudness", side_effect=fake_master_loudness):
            ok_master = run_stage_master(ctx)

        self.assertTrue(ok_master)
        final_out = ctx.chapter_dir / ctx.output_name
        self.assertTrue(final_out.exists())
        self.assertEqual(final_out.read_bytes(), b"MASTERED_MP4_DATA")
        self.assertTrue((ctx.chapter_dir / "video.mp4").exists())
        self.assertFalse(ctx.scratch_manager.chapter_work_dir("gate1_ch").exists())

    def test_gate1_2_stage_master_backward_compat_legacy_prenorm_in_chapter_dir(self):
        ctx = self._make_context("legacy_ch")
        legacy_prenorm = ctx.chapter_dir / "video.prenorm.mkv"
        legacy_prenorm.write_bytes(b"LEGACY_MKV")

        def fake_master_loudness(src, dst, **kwargs):
            self.assertEqual(Path(src), legacy_prenorm)
            Path(dst).write_bytes(b"LEGACY_MASTERED_MP4")
            return {"input_i": -14.0}

        with patch("src.pipeline.stage_video_master.master_loudness", side_effect=fake_master_loudness):
            ok = run_stage_master(ctx)

        self.assertTrue(ok)
        self.assertFalse(legacy_prenorm.exists())
        self.assertEqual((ctx.chapter_dir / ctx.output_name).read_bytes(), b"LEGACY_MASTERED_MP4")

    def test_gate1_2_bench_mode_uses_remotion_runner_instead_of_cli(self):
        ctx = self._make_context("bench_ch", frames="0-239", bench="opt1")
        captured = {}

        def fake_render(self_runner, **kwargs):
            captured.update(kwargs)
            out_p = Path(kwargs["output_path"])
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_bytes(b"BENCH_MKV")
            self_runner.last_timing = {"bundle_ms": 80, "select_ms": 300, "render_ms": 6000, "cache_hit": True}
            return True

        with patch.object(RemotionRunner, "render", autospec=True, side_effect=fake_render):
            ok = run_stage_video(ctx)

        self.assertTrue(ok)
        self.assertEqual(captured["frame_range"], "0-239")
        bench_file = ctx.chapter_dir / "bench_opt1.json"
        self.assertTrue(bench_file.exists())
        data = json.loads(bench_file.read_text(encoding="utf-8"))
        self.assertEqual(data["frames"], 240)
        self.assertEqual(data["bundle_ms"], 80)
        self.assertEqual(data["render_ms"], 6000)
        self.assertAlmostEqual(data["fps_render"], 40.0, places=1)

    def test_gate1_3_remotion_runner_command_and_timing_parser(self):
        runner = RemotionRunner(project_root=self.root)
        cmd = runner.build_command(
            props_path=self.tmp_dir / "props.json",
            output_path=self.tmp_dir / "out.mkv",
            concurrency=20,
            crf=18,
            gl="swangle",
            x264_preset="veryfast",
            image_format="jpeg",
            jpeg_quality=85,
            frame_range="0-239",
            scratch_dir=self.tmp_dir / "scratch",
            chapter_id="sample_chapter",
            bundle_cache=False,
        )
        # Giữ vị trí tương thích ngược: [npx, tsx, scripts/render.ts, props, out, conc, crf, ...]
        self.assertEqual(cmd[1:3], ["tsx", "scripts/render.ts"])
        self.assertEqual(cmd[5], "20")
        self.assertEqual(cmd[6], "18")
        self.assertIn("--gl", cmd)
        self.assertIn("swangle", cmd)
        self.assertIn("--x264-preset", cmd)
        self.assertIn("veryfast", cmd)
        self.assertIn("--frames", cmd)
        self.assertIn("0-239", cmd)
        self.assertIn("--scratch-dir", cmd)
        self.assertIn("--chapter-id", cmd)
        self.assertIn("--no-bundle-cache", cmd)

        timing = runner.parse_timing_line("TIMING bundle_ms=145 select_ms=520 render_ms=7310")
        self.assertEqual(timing, {"bundle_ms": 145, "select_ms": 520, "render_ms": 7310})

        cache_info = runner.parse_bundle_cache_line("BUNDLE_CACHE hit=1 hash=a1b2c3d4e5f60708 sync_ms=12 synced_files=0")
        self.assertEqual(
            cache_info,
            {"cache_hit": True, "source_hash": "a1b2c3d4e5f60708", "sync_ms": 12, "synced_files": 0},
        )

    def test_gate1_3_bundle_cache_ts_hash_sync_and_prune(self):
        """Kiểm thử trực tiếp computeSourceHash, syncDirectoryIncremental và pruneOldBundles qua tsx."""
        npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"
        script = (
            "import fs from 'node:fs'; import path from 'node:path'; "
            "import { computeSourceHash, syncDirectoryIncremental, pruneOldBundles } from './scripts/bundle-cache'; "
            f"const base = {json.dumps(str(self.tmp_dir / 'bc_test'))}; "
            "const remDir = path.join(base, 'rem'); "
            "fs.mkdirSync(path.join(remDir, 'src'), { recursive: true }); "
            "fs.writeFileSync(path.join(remDir, 'src', 'index.ts'), 'export const a = 1;'); "
            "fs.writeFileSync(path.join(remDir, 'package.json'), '{}'); "
            "const h1 = computeSourceHash(remDir); "
            "const h2 = computeSourceHash(remDir); "
            "fs.writeFileSync(path.join(remDir, 'src', 'index.ts'), 'export const a = 2;'); "
            "const h3 = computeSourceHash(remDir); "
            "const srcPub = path.join(base, 'pub_src'); const dstPub = path.join(base, 'pub_dst'); "
            "fs.mkdirSync(srcPub, { recursive: true }); "
            "fs.writeFileSync(path.join(srcPub, 'a.txt'), 'hello'); "
            "const c1 = syncDirectoryIncremental(srcPub, dstPub); "
            "const c2 = syncDirectoryIncremental(srcPub, dstPub); "
            "fs.writeFileSync(path.join(srcPub, 'a.txt'), 'hello_changed'); "
            "const c3 = syncDirectoryIncremental(srcPub, dstPub); "
            "const cacheDir = path.join(base, 'cache'); "
            "for (const name of ['h1', 'h2', 'h3', 'h4']) { "
            "  const d = path.join(cacheDir, name); fs.mkdirSync(d, { recursive: true }); "
            "  fs.writeFileSync(path.join(d, '.bundle-complete'), '{}'); "
            "} "
            "pruneOldBundles(cacheDir, 'h4', 2); "
            "const remaining = fs.readdirSync(cacheDir).sort(); "
            "console.log(JSON.stringify({ h1, h2, h3, c1, c2, c3, remaining }));"
        )
        res = subprocess.run(
            [npx_cmd, "tsx", "-e", script],
            cwd=str(self.root / "remotion"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=True,
        )
        out = json.loads(res.stdout.strip().splitlines()[-1])
        self.assertEqual(len(out["h1"]), 16)
        self.assertEqual(out["h1"], out["h2"])
        self.assertNotEqual(out["h1"], out["h3"])
        self.assertEqual(out["c1"], 1)
        self.assertEqual(out["c2"], 0)  # Cache hit incremental sync: 0 file copied
        self.assertEqual(out["c3"], 1)  # Modified file synced
        self.assertEqual(len(out["remaining"]), 2)
        self.assertIn("h4", out["remaining"])

    def test_gate1_4_benchmark_selection_and_settings_apply(self):
        runs = [
            {"gl": "angle", "concurrency": 24, "x264_preset": "faster", "fps_render": 45.0, "peak_vram_mb": 3800.0, "peak_ram_gb": 30.0, "success": True},
            {"gl": "angle", "concurrency": 20, "x264_preset": "faster", "fps_render": 40.0, "peak_vram_mb": 3000.0, "peak_ram_gb": 50.0, "success": True},
            {"gl": "angle", "concurrency": 16, "x264_preset": "faster", "fps_render": 35.0, "peak_vram_mb": 2600.0, "peak_ram_gb": 32.0, "success": True},
            {"gl": "swangle", "concurrency": 24, "x264_preset": "faster", "fps_render": 38.0, "peak_vram_mb": 900.0, "peak_ram_gb": 36.0, "success": True},
        ]
        best = select_best_config(runs, max_vram_mb=3400.0, max_ram_gb=48.0)
        self.assertIsNotNone(best)
        self.assertEqual(best["gl"], "swangle")
        self.assertEqual(best["concurrency"], 24)

        fake_settings = self.tmp_dir / "settings.json"
        fake_settings.write_text(
            json.dumps({"render": {"renderer": "ffmpeg", "crf": 18, "concurrency": None}}),
            encoding="utf-8",
        )
        updated = apply_config_to_settings(fake_settings, best)
        self.assertEqual(updated["renderer"], "ffmpeg")
        self.assertEqual(updated["crf"], 18)
        self.assertEqual(updated["gl"], "swangle")
        self.assertEqual(updated["concurrency"], 24)
        self.assertEqual(updated["x264_preset"], "faster")

    def test_gate1_4_bench_hw_matrix_artifact_if_present(self):
        matrix_path = self.root / "output" / "sample_chapter" / "bench_hw_matrix.json"
        if not matrix_path.exists():
            self.skipTest("bench_hw_matrix.json chưa được tạo bởi benchmark_hardware.py")

        data = json.loads(matrix_path.read_text(encoding="utf-8"))
        self.assertIn("runs", data)
        self.assertIn("best", data)
        self.assertIsNotNone(data["best"])
        self.assertGreater(data["best"]["fps_render"], 15.29)

        cache_hits = [r for r in data["runs"] if r.get("cache_hit")]
        self.assertGreater(len(cache_hits), 0, "Phải có ít nhất 1 lần chạy bundle cache hit")
        self.assertLess(min(r["bundle_ms"] for r in cache_hits), 500)

    def test_audit_ffmpeg_stage_all_runs_master_so_output_is_promoted(self):
        """--renderer ffmpeg --stage all phải gọi run_stage_master để promote video từ NVMe scratch về output/."""
        fake_ctx = self._make_context("ffmpeg_all_ch")
        fake_ctx.renderer = "ffmpeg"
        fake_ctx.stage = "all"

        with patch("src.pipeline.runner.os.path.exists", return_value=True), \
             patch("src.pipeline.runner.PipelineContext.create", return_value=fake_ctx), \
             patch("src.pipeline.runner.run_stage_script", return_value=object()) as m_script, \
             patch("src.pipeline.runner.run_stage_audio", return_value=object()) as m_audio, \
             patch("src.pipeline.runner.run_stage_assets", return_value=True) as m_assets, \
             patch("src.pipeline.runner.run_stage_props", return_value=True) as m_props, \
             patch("src.pipeline.runner.run_stage_video", return_value=True) as m_video, \
             patch("src.pipeline.runner.run_stage_master", return_value=True) as m_master, \
             patch("src.pipeline.runner.run_stage_package", return_value=True) as m_package:
            ok = execute_pipeline(
                chapter_file="input/sample_chapter.txt",
                renderer="ffmpeg",
                stage="all",
            )

        self.assertTrue(ok)
        m_script.assert_called_once()
        m_audio.assert_called_once()
        m_assets.assert_called_once()
        m_props.assert_called_once()
        m_video.assert_called_once()
        m_master.assert_called_once()
        m_package.assert_not_called()

    def test_audit_find_prenorm_path_respects_active_renderer(self):
        """Khi cả .mkv và .mov cùng tồn tại trên scratch, phải ưu tiên đúng loại của renderer hiện tại."""
        ctx_ff = self._make_context("dual_prenorm")
        ctx_ff.renderer = "ffmpeg"
        mkv = ctx_ff.scratch_manager.prenorm_mkv_path("dual_prenorm")
        mov = ctx_ff.scratch_manager.prenorm_mov_path("dual_prenorm", ctx_ff.output_name)
        mkv.parent.mkdir(parents=True, exist_ok=True)
        mkv.write_bytes(b"MKV")
        mov.write_bytes(b"MOV")

        self.assertEqual(_find_prenorm_path(ctx_ff), mov)

        ctx_ff.renderer = "remotion"
        self.assertEqual(_find_prenorm_path(ctx_ff), mkv)

    def test_audit_remotion_runner_watchdog_enforces_timeout_on_hanging_process(self):
        """Timeout phải thực sự ngắt tiến trình con treo im lặng khi stdout đang mở."""
        props = self.tmp_dir / "props.json"
        props.write_text("{}", encoding="utf-8")
        out = self.tmp_dir / "out.mkv"

        runner = RemotionRunner(project_root=self.root, timeout_sec=1)
        sleep_cmd = [sys.executable, "-c", "import time; time.sleep(10)"]
        with patch.object(runner, "build_command", return_value=sleep_cmd):
            ok = runner.render(props_path=props, output_path=out)
        self.assertFalse(ok)

    def test_audit_prune_old_bundles_preserves_dot_dirs(self):
        """pruneOldBundles không được xóa thư mục ẩn .empty-public dùng cho bundler."""
        npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"
        script = (
            "import fs from 'node:fs'; import path from 'node:path'; "
            "import { pruneOldBundles } from './scripts/bundle-cache'; "
            f"const cacheDir = {json.dumps(str(self.tmp_dir / 'dot_prune'))}; "
            "for (const name of ['.empty-public', 'h1', 'h2', 'h3']) { "
            "  const d = path.join(cacheDir, name); fs.mkdirSync(d, { recursive: true }); "
            "  if (!name.startsWith('.')) fs.writeFileSync(path.join(d, '.bundle-complete'), '{}'); "
            "} "
            "pruneOldBundles(cacheDir, 'h3', 2); "
            "console.log(JSON.stringify(fs.readdirSync(cacheDir).sort()));"
        )
        res = subprocess.run(
            [npx_cmd, "tsx", "-e", script],
            cwd=str(self.root / "remotion"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=True,
        )
        remaining = json.loads(res.stdout.strip().splitlines()[-1])
        self.assertIn(".empty-public", remaining)
        self.assertIn("h3", remaining)
        self.assertEqual(len([x for x in remaining if not x.startswith(".")]), 2)


if __name__ == "__main__":
    unittest.main()
