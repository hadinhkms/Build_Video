import json
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.hardware_profile import HardwareProfile
from src.core.models import Shot, ShotKind, Storyboard
from src.core.scratch_manager import ScratchManager
from src.core.state_manager import StateManager
from src.pipeline.context import PipelineContext
from src.pipeline.stage_video_master import run_stage_video
from src.render.encoder_probe import EncoderCapability
from src.video_composer import VideoComposer


def _make_nvenc_cap(supports_bframes: bool = True, max_parallel: int = 3) -> EncoderCapability:
    return EncoderCapability(
        selected_encoder="h264_nvenc",
        requested_encoder="auto",
        nvenc_available=True,
        supports_bframes=supports_bframes,
        ffmpeg_bin_dir=Path("C:/ffmpeg/bin"),
        max_parallel_nvenc=max_parallel,
        probe_ms=100,
        reason="nvenc_bframes_ok" if supports_bframes else "nvenc_no_bframes_ok",
    )


def _make_cpu_cap() -> EncoderCapability:
    return EncoderCapability(
        selected_encoder="libx264",
        requested_encoder="libx264",
        nvenc_available=False,
        supports_bframes=False,
        ffmpeg_bin_dir=Path("C:/ffmpeg/bin"),
        max_parallel_nvenc=0,
        probe_ms=1,
        reason="forced_libx264",
    )


class TestVideoComposerParallel(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.settings_path = self.tmp_dir / "settings.json"
        self.settings_path.write_text(
            json.dumps(
                {
                    "video": {"width": 1920, "height": 1080, "fps": 24, "crf": 19, "preset": "medium"},
                    "render": {
                        "renderer": "ffmpeg",
                        "encoder": "auto",
                        "nvenc_preset": "p5",
                        "nvenc_cq": 19,
                        "ffmpeg_workers": "auto",
                        "x264_preset": "faster",
                        "crf": 18,
                    },
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_ken_burns_filter_uses_optimized_scale_dimensions(self):
        composer = VideoComposer(settings_path=str(self.settings_path), encoder_capability=_make_cpu_cap())
        self.assertIn("scale=2304:-2,", composer._get_ken_burns_filter("zoom_in", 4.0))
        self.assertIn("scale=2304:-2,", composer._get_ken_burns_filter("zoom_out", 4.0))
        self.assertIn("scale=2160:-2,", composer._get_ken_burns_filter("pan_left", 4.0))
        self.assertIn("scale=2160:-2,", composer._get_ken_burns_filter("pan_right", 4.0))

    def test_nvenc_and_libx264_command_generation(self):
        c_turing = VideoComposer(
            settings_path=str(self.settings_path),
            encoder_capability=_make_nvenc_cap(supports_bframes=True),
        )
        cmd_nv = c_turing.build_render_shot_command("img.jpg", "a.mp3", "out.mov", "zoom_in", 4.0)
        self.assertIn("h264_nvenc", cmd_nv)
        self.assertIn("-preset", cmd_nv)
        self.assertEqual(cmd_nv[cmd_nv.index("-preset") + 1], "p5")
        self.assertEqual(cmd_nv[cmd_nv.index("-cq") + 1], "19")
        self.assertEqual(cmd_nv[cmd_nv.index("-bf") + 1], "2")
        self.assertEqual(cmd_nv[cmd_nv.index("-spatial-aq") + 1], "1")
        self.assertEqual(cmd_nv[cmd_nv.index("-pix_fmt") + 1], "yuv420p")
        self.assertEqual(cmd_nv[cmd_nv.index("-c:a") + 1], "pcm_s16le")

        c_volta = VideoComposer(
            settings_path=str(self.settings_path),
            encoder_capability=_make_nvenc_cap(supports_bframes=False),
        )
        cmd_volta = c_volta.build_render_shot_command("img.jpg", "a.mp3", "out.mov", "zoom_in", 4.0)
        self.assertEqual(cmd_volta[cmd_volta.index("-bf") + 1], "0")

        c_cpu = VideoComposer(
            settings_path=str(self.settings_path),
            encoder_capability=_make_cpu_cap(),
        )
        cmd_cpu = c_cpu.build_render_shot_command("img.jpg", "a.mp3", "out.mov", "pan_left", 4.0)
        self.assertIn("libx264", cmd_cpu)
        self.assertEqual(cmd_cpu[cmd_cpu.index("-preset") + 1], "faster")
        self.assertEqual(cmd_cpu[cmd_cpu.index("-crf") + 1], "18")
        self.assertEqual(cmd_cpu[cmd_cpu.index("-threads") + 1], "4")

    def test_recommended_workers_respects_nvenc_cap_and_cpu_cores(self):
        c_nv = VideoComposer(
            settings_path=str(self.settings_path),
            encoder_capability=_make_nvenc_cap(max_parallel=3),
        )
        self.assertEqual(c_nv.get_recommended_workers(physical_cores=28), 3)
        c_nv.ffmpeg_workers_setting = 8
        # Dù cấu hình đặt 8, vẫn bị chặn cứng ở max_parallel_nvenc (3) để tránh tràn phiên NVENC
        self.assertEqual(c_nv.get_recommended_workers(physical_cores=28), 3)

        c_cpu = VideoComposer(
            settings_path=str(self.settings_path),
            encoder_capability=_make_cpu_cap(),
        )
        self.assertEqual(c_cpu.get_recommended_workers(physical_cores=28), 12)
        self.assertEqual(c_cpu.get_recommended_workers(physical_cores=8), 4)

    def test_nvenc_semaphore_enforces_concurrent_limit(self):
        composer = VideoComposer(
            settings_path=str(self.settings_path),
            encoder_capability=_make_nvenc_cap(max_parallel=3),
        )
        lock = threading.Lock()
        active = 0
        peak = 0

        def fake_subproc(cmd, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.06)
            with lock:
                active -= 1
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

        with patch("src.video_composer.subprocess.run", side_effect=fake_subproc):
            threads = [
                threading.Thread(
                    target=composer.render_shot_clip,
                    args=("img.jpg", "aud.mp3", str(self.tmp_dir / f"s_{i}.mov"), "zoom_in", 4.0),
                )
                for i in range(8)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertLessEqual(peak, 3, f"Số phiên NVENC song song vượt ngưỡng 3 (peak={peak})")
        self.assertGreaterEqual(peak, 2, "Phải thực sự chạy song song nhiều phiên")

    def test_nvenc_runtime_failure_falls_back_to_libx264_in_auto_mode(self):
        composer = VideoComposer(
            settings_path=str(self.settings_path),
            encoder_capability=_make_nvenc_cap(),
        )
        seen_cmds = []

        def fake_run(cmd, **kwargs):
            seen_cmds.append(cmd)
            if "h264_nvenc" in cmd:
                raise subprocess.CalledProcessError(1, cmd, stderr=b"OpenEncodeSessionEx failed: out of memory")
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

        with patch("src.video_composer.subprocess.run", side_effect=fake_run):
            ok = composer.render_shot_clip("img.jpg", "aud.mp3", str(self.tmp_dir / "fb.mov"), "zoom_in", 4.0)

        self.assertTrue(ok)
        self.assertEqual(len(seen_cmds), 2)
        self.assertIn("h264_nvenc", seen_cmds[0])
        self.assertIn("libx264", seen_cmds[1])

    def test_parallel_stage_video_preserves_exact_shot_and_srt_order(self):
        """Dù các shot kết thúc lệch thứ tự khi chạy ThreadPoolExecutor, thứ tự concat & SRT phải chuẩn 100%."""
        chapter_id = "par_order_ch"
        chapter_dir = self.tmp_dir / "output" / chapter_id
        audio_dir = chapter_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        sb_path = chapter_dir / "storyboard.json"

        shots = [
            Shot(
                shot_id=f"shot_{i:02d}",
                kind=ShotKind.STORY,
                raw_text=f"Câu thứ {i}.",
                voice_text=f"Câu thứ {i}.",
                duration=4.0 + i * 0.5,
                camera_motion="zoom_in" if i % 2 == 0 else "pan_left",
                audio_file=str(audio_dir / f"shot_{i:02d}.mp3"),
            )
            for i in range(6)
        ]
        state_mgr = StateManager(str(sb_path))
        state_mgr.save_state(Storyboard(chapter_id=chapter_id, title="Test", shots=shots))

        scratch_dir = self.tmp_dir / "nvme_scratch"
        hw = HardwareProfile(
            cpu_name="Xeon",
            cpu_physical_cores=28,
            cpu_logical_threads=56,
            cpu_sockets=2,
            numa_nodes=2,
            ram_total_gb=64.0,
            ram_available_gb=40.0,
            has_nvidia=True,
            gpu_name="GTX 1650",
            vram_mb=4096,
            gpu_driver="610.88",
            workspace_path=str(self.root),
            workspace_drive="D:",
            workspace_disk_type="USB",
            workspace_disk_detail="USB HDD",
            workspace_free_gb=500.0,
            localappdata_path=str(scratch_dir),
            localappdata_drive="C:",
            localappdata_disk_type="NVMe",
            localappdata_disk_detail="NVMe SSD",
            localappdata_free_gb=300.0,
        )
        scratch_mgr = ScratchManager(
            project_root=self.root,
            scratch_dir_setting=str(scratch_dir),
            hardware_profile=hw,
        )
        ctx = PipelineContext(
            chapter_file="input/sample_chapter.txt",
            output_name="final_chapter_video.mp4",
            tts_provider="edge",
            renderer="ffmpeg",
            stage="video",
            title="Test",
            env=None,
            frames=None,
            bench=None,
            settings={
                "video": {"fps": 24},
                "render": {
                    "renderer": "ffmpeg",
                    "encoder": "auto",
                    "nvenc_preset": "p5",
                    "nvenc_cq": 19,
                    "ffmpeg_workers": "auto",
                },
            },
            story_rules={},
            fps=24,
            shot_min=4.0,
            shot_max=6.5,
            split_min=2.5,
            chapter_id=chapter_id,
            chapter_dir=chapter_dir,
            audio_dir=audio_dir,
            storyboard_path=sb_path,
            state_mgr=state_mgr,
            hardware_profile=hw,
            scratch_manager=scratch_mgr,
        )

        # Shot đầu ngủ lâu hơn shot sau để cố tình hoàn tất đảo ngược thứ tự
        def fake_render_shot(self_c, image_path, audio_path, output_clip_path, motion_type="zoom_in", duration=5.0):
            idx_num = int(Path(output_clip_path).stem.split("_")[1])
            time.sleep((6 - idx_num) * 0.015)
            Path(output_clip_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_clip_path).write_bytes(f"CLIP_{idx_num}".encode("utf-8"))
            return True

        captured_concat = {}

        def fake_concat(self_c, clip_paths, output_video_path):
            captured_concat["clips"] = list(clip_paths)
            captured_concat["out"] = output_video_path
            Path(output_video_path).write_bytes(b"PRENORM_MOV")
            return True

        with patch("src.pipeline.stage_video_master.probe_encoder_capability", return_value=_make_nvenc_cap(max_parallel=3)), \
             patch.object(VideoComposer, "render_shot_clip", autospec=True, side_effect=fake_render_shot), \
             patch.object(VideoComposer, "probe_duration", side_effect=lambda p: 4.0 + int(Path(p).stem.split("_")[1]) * 0.5), \
             patch.object(VideoComposer, "concatenate_shots", autospec=True, side_effect=fake_concat):
            ok = run_stage_video(ctx)

        self.assertTrue(ok)
        # Kiểm tra clip và prenorm đều nằm trên NVMe scratch
        expected_clip_names = [f"shot_{i:02d}.mov" for i in range(6)]
        self.assertEqual([Path(p).name for p in captured_concat["clips"]], expected_clip_names)
        self.assertEqual(Path(captured_concat["out"]), scratch_mgr.prenorm_mov_path(chapter_id, ctx.output_name))
        for p in captured_concat["clips"]:
            self.assertEqual(Path(p).parent, scratch_mgr.clips_dir(chapter_id))

        # Kiểm tra SRT đúng thứ tự Câu thứ 0 -> Câu thứ 5
        srt_text = (chapter_dir / "final_chapter_video.srt").read_text(encoding="utf-8")
        positions = [srt_text.index(f"Câu thứ {i}.") for i in range(6)]
        self.assertEqual(positions, sorted(positions))

    def test_nvenc_semaphore_clamped_to_max_four_sessions(self):
        composer = VideoComposer(
            settings_path=str(self.settings_path),
            encoder_capability=_make_nvenc_cap(max_parallel=8),
        )
        # Dù capability báo 8, BoundedSemaphore vẫn bị chặn trần 4 phiên GeForce
        self.assertIsNotNone(composer._nvenc_semaphore)
        self.assertEqual(composer._nvenc_semaphore._initial_value, 4)

    def test_parallel_stage_video_aborts_on_single_shot_failure_or_exception(self):
        """Nếu 1 shot thất bại hoặc ném exception trong ThreadPoolExecutor, phải trả False và KHÔNG ghi SRT/concat lệch."""
        for fail_mode in ("return_false", "raise_exception"):
            chapter_id = f"fail_ch_{fail_mode}"
            chapter_dir = self.tmp_dir / "output" / chapter_id
            audio_dir = chapter_dir / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            sb_path = chapter_dir / "storyboard.json"

            shots = [
                Shot(
                    shot_id=f"shot_{i:02d}",
                    kind=ShotKind.STORY,
                    raw_text=f"Câu {i}.",
                    voice_text=f"Câu {i}.",
                    duration=4.0,
                    camera_motion="zoom_in",
                    audio_file=str(audio_dir / f"shot_{i:02d}.mp3"),
                )
                for i in range(4)
            ]
            state_mgr = StateManager(str(sb_path))
            state_mgr.save_state(Storyboard(chapter_id=chapter_id, title="FailTest", shots=shots))

            scratch_dir = self.tmp_dir / f"scratch_{fail_mode}"
            hw = HardwareProfile(
                cpu_name="Xeon",
                cpu_physical_cores=28,
                cpu_logical_threads=56,
                cpu_sockets=2,
                numa_nodes=2,
                ram_total_gb=64.0,
                ram_available_gb=40.0,
                has_nvidia=True,
                gpu_name="GTX 1650",
                vram_mb=4096,
                gpu_driver="610.88",
                workspace_path=str(self.root),
                workspace_drive="D:",
                workspace_disk_type="USB",
                workspace_disk_detail="USB HDD",
                workspace_free_gb=500.0,
                localappdata_path=str(scratch_dir),
                localappdata_drive="C:",
                localappdata_disk_type="NVMe",
                localappdata_disk_detail="NVMe SSD",
                localappdata_free_gb=300.0,
            )
            scratch_mgr = ScratchManager(
                project_root=self.root,
                scratch_dir_setting=str(scratch_dir),
                hardware_profile=hw,
            )
            ctx = PipelineContext(
                chapter_file="input/sample_chapter.txt",
                output_name="final_chapter_video.mp4",
                tts_provider="edge",
                renderer="ffmpeg",
                stage="video",
                title="FailTest",
                env=None,
                frames=None,
                bench=None,
                settings={
                    "video": {"fps": 24},
                    "render": {"renderer": "ffmpeg", "encoder": "nvenc", "ffmpeg_workers": 3},
                },
                story_rules={},
                fps=24,
                shot_min=4.0,
                shot_max=6.5,
                split_min=2.5,
                chapter_id=chapter_id,
                chapter_dir=chapter_dir,
                audio_dir=audio_dir,
                storyboard_path=sb_path,
                state_mgr=state_mgr,
                hardware_profile=hw,
                scratch_manager=scratch_mgr,
            )

            seen_encoder_settings = set()

            def fake_render_shot(self_c, image_path, audio_path, output_clip_path, motion_type="zoom_in", duration=5.0):
                seen_encoder_settings.add(self_c.encoder_setting)
                if Path(output_clip_path).stem == "shot_02":
                    if fail_mode == "raise_exception":
                        raise OSError("Simulated worker disk error")
                    return False
                Path(output_clip_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_clip_path).write_bytes(b"OK")
                return True

            with patch("src.pipeline.stage_video_master.probe_encoder_capability", return_value=_make_nvenc_cap(max_parallel=3)), \
                 patch.object(VideoComposer, "render_shot_clip", autospec=True, side_effect=fake_render_shot), \
                 patch.object(VideoComposer, "probe_duration", return_value=4.0), \
                 patch.object(VideoComposer, "concatenate_shots", autospec=True) as mock_concat:
                ok = run_stage_video(ctx)

            self.assertFalse(ok, f"Phải trả False khi 1 shot lỗi ({fail_mode})")
            mock_concat.assert_not_called()
            self.assertFalse((chapter_dir / "final_chapter_video.srt").exists())
            self.assertEqual(seen_encoder_settings, {"nvenc"})


if __name__ == "__main__":
    unittest.main()
