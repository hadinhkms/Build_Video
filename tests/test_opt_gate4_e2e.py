import json
import os
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

import numpy as np

from scripts.benchmark_e2e_report import (
    format_markdown_report,
    parse_srt_timestamps,
    verify_e2e_invariants,
)
from src.core.models import Shot, ShotKind, Storyboard
from src.export.crop_utils import (
    clear_media_duration_cache,
    copy_file_if_different,
    get_media_duration,
)
from src.visuals.asset_packager import AssetPackager

ROOT = Path(__file__).resolve().parent.parent
HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


class TestOptGate4E2E(unittest.TestCase):
    """Kiểm thử nghiệm thu OPT Phase 4: settings, hardlink-first, ffprobe cache, parallel packager & E2E report."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        clear_media_duration_cache()

    def test_settings_json_contains_opt_phase4_keys(self):
        settings = json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["audio"]["tts_concurrency"], 5)
        self.assertEqual(settings["visuals"]["rembg_threads"], "auto")
        self.assertEqual(settings["visuals"]["rembg_device"], "auto")

    def test_copy_file_if_different_uses_hardlink_first_and_safe_fallback(self):
        src = self.tmp / "assets" / "plate.jpg"
        dst = self.tmp / "public" / "plate.jpg"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(b"PLATE_IMAGE_CONTENT_12345")

        # 1. Lần đầu cùng ổ đĩa -> tạo hardlink NTFS
        changed1 = copy_file_if_different(src, dst)
        self.assertTrue(changed1)
        self.assertTrue(dst.exists())
        self.assertTrue(os.path.samefile(src, dst))

        # 2. Lần 2 cùng inode -> bỏ qua tức thì
        changed2 = copy_file_if_different(src, dst)
        self.assertFalse(changed2)

        # 3. Đích là 1 file khác inode -> gỡ & link lại tới src
        other = self.tmp / "other.jpg"
        other.write_bytes(b"OLD_DIFFERENT_INODE")
        os.replace(other, dst)
        self.assertFalse(os.path.samefile(src, dst))

        changed3 = copy_file_if_different(src, dst)
        self.assertTrue(changed3)
        self.assertTrue(os.path.samefile(src, dst))
        self.assertEqual(dst.read_bytes(), b"PLATE_IMAGE_CONTENT_12345")

        # 4. Fallback sạch sang atomic copy khi os.link báo OSError (khác FS / không hỗ trợ link)
        src2 = self.tmp / "assets" / "plate2.jpg"
        src2.write_bytes(b"FALLBACK_CONTENT_99999")
        # dst hiện đang là hardlink trỏ tới `src` -> fallback copy KHÔNG được làm hỏng `src`!
        with mock.patch("src.export.crop_utils.os.link", side_effect=OSError("EXDEV")):
            changed4 = copy_file_if_different(src2, dst)
        self.assertTrue(changed4)
        self.assertEqual(dst.read_bytes(), b"FALLBACK_CONTENT_99999")
        self.assertEqual(src.read_bytes(), b"PLATE_IMAGE_CONTENT_12345")
        self.assertFalse(os.path.samefile(src, dst))

    def test_get_media_duration_caches_by_resolved_path_mtime_and_size(self):
        media = self.tmp / "clip.mp4"
        media.write_bytes(b"DUMMY_MEDIA_V1")

        fake_proc = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout="4.250\n", stderr=""
        )
        with mock.patch("src.export.crop_utils.subprocess.run", return_value=fake_proc) as m_run:
            d1 = get_media_duration(media)
            d2 = get_media_duration(media)
            self.assertEqual(d1, 4.25)
            self.assertEqual(d2, 4.25)
            self.assertEqual(m_run.call_count, 1)

            # Thay đổi kích thước tệp -> cache miss
            media.write_bytes(b"DUMMY_MEDIA_V2_LONGER")
            fake_proc2 = subprocess.CompletedProcess(
                args=["ffprobe"], returncode=0, stdout="6.500\n", stderr=""
            )
            m_run.return_value = fake_proc2
            d3 = get_media_duration(media)
            self.assertEqual(d3, 6.5)
            self.assertEqual(m_run.call_count, 2)

    @unittest.skipUnless(HAS_FFMPEG, "cần ffmpeg/ffprobe")
    def test_asset_packager_cuts_voice_wavs_in_parallel(self):
        audio_dir = self.tmp / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        wav = audio_dir / "voice.wav"
        samples = (np.sin(np.linspace(0, 30, 16000 * 3)) * 32767).astype(np.int16)
        with wave.open(str(wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(samples.tobytes())

        shots = [
            Shot(
                shot_id=f"shot_{i:02d}",
                kind=ShotKind.STORY,
                action=f"Hành động {i}",
                camera_motion="zoom_in",
                duration_frames=24,
                audio_file=str(wav),
                audio_start_in_file_sec=float(i * 0.2),
            )
            for i in range(6)
        ]
        sb = Storyboard(chapter_id="par_pkg", title="Parallel Pkg", shots=shots)
        packager = AssetPackager(base_dir=self.tmp)
        out_dir = packager.export_hybrid_package(
            storyboard=sb,
            chapter_id="par_pkg",
            output_root=self.tmp / "packages",
            fps=24,
        )
        for i in range(6):
            voice_out = out_dir / f"shot_{i:02d}" / "voice.wav"
            self.assertTrue(voice_out.exists(), f"Thiếu {voice_out}")
            self.assertGreater(voice_out.stat().st_size, 100)

    def test_e2e_invariant_verifier_and_markdown_formatter(self):
        ch_dir = self.tmp / "output" / "gate4_sim"
        ch_dir.mkdir(parents=True, exist_ok=True)
        props_path = ch_dir / "render_props.json"
        props_path.write_text(
            json.dumps({
                "fps": 24,
                "scenes": [
                    {"id": "s1", "durationInFrames": 120},
                    {"id": "s2", "durationInFrames": 120},
                ],
            }),
            encoding="utf-8",
        )
        srt_path = ch_dir / "video.srt"
        srt_path.write_text(
            "1\n00:00:00,000 --> 00:00:04,500\nCâu một.\n\n"
            "2\n00:00:05,000 --> 00:00:09,500\nCâu hai.\n",
            encoding="utf-8",
        )
        (ch_dir / "video.mp4").write_bytes(b"MP4")
        (ch_dir / "youtube_metadata.json").write_text("{}", encoding="utf-8")
        (ch_dir / "thumbnail_base.png").write_bytes(b"PNG")
        (ch_dir / "render_report.json").write_text("{}", encoding="utf-8")

        spans = parse_srt_timestamps(srt_path)
        self.assertEqual(spans, [(0.0, 4.5), (5.0, 9.5)])

        clean_work = self.tmp / "nvme_work" / "gate4_sim"
        fake_probe = {
            "duration_sec": 10.02,  # 240f @ 24fps = 10.0s -> delta = 0.48f <= 1f
            "video_codec": "h264",
            "video_width": 1920,
            "video_height": 1080,
            "video_stream_count": 1,
            "audio_codec": "aac",
            "audio_sample_rate": 44100,
            "audio_channels": 2,
            "audio_stream_count": 1,
            "size_mb": 12.3,
        }
        fake_loud = {"input_i": "-14.05", "input_tp": "-1.62", "input_lra": "6.50"}

        with mock.patch("scripts.benchmark_e2e_report.probe_media_info", return_value=fake_probe), \
             mock.patch("scripts.benchmark_e2e_report.measure_loudness", return_value=fake_loud):
            inv = verify_e2e_invariants(
                chapter_dir=ch_dir,
                props_path=props_path,
                video_path=ch_dir / "video.mp4",
                srt_path=srt_path,
                scratch_work_dir=clean_work,
            )

        self.assertTrue(inv["all_passed"])
        self.assertTrue(inv["frame_duration"]["passed"])
        self.assertTrue(inv["audio_stream"]["passed"])
        self.assertTrue(inv["loudness"]["passed"])
        self.assertTrue(inv["srt_sync"]["passed"])
        self.assertTrue(inv["nvme_scratch_clean"]["passed"])

        # Nếu còn file rác trên NVMe scratch -> nvme_scratch_clean phải FAIL
        clean_work.mkdir(parents=True, exist_ok=True)
        (clean_work / "video.prenorm.mkv").write_bytes(b"LEFTOVER")
        with mock.patch("scripts.benchmark_e2e_report.probe_media_info", return_value=fake_probe), \
             mock.patch("scripts.benchmark_e2e_report.measure_loudness", return_value=fake_loud):
            inv_dirty = verify_e2e_invariants(
                chapter_dir=ch_dir,
                props_path=props_path,
                video_path=ch_dir / "video.mp4",
                srt_path=srt_path,
                scratch_work_dir=clean_work,
            )
        self.assertFalse(inv_dirty["nvme_scratch_clean"]["passed"])
        self.assertFalse(inv_dirty["all_passed"])

        # Định dạng bảng Markdown hợp lệ
        md = format_markdown_report([
            {
                "chapter_id": "gate4_sim",
                "pipeline_ok": True,
                "stage_timings_sec": {
                    "script": 0.05, "audio": 1.2, "assets": 0.1,
                    "props": 0.4, "props_warm": 0.15, "video": 25.0,
                    "master": 3.5, "package": 4.2, "total": 34.6,
                },
                "render_metrics": {
                    "fps_render": 42.5, "encoder": "h264_nvenc",
                    "concurrency": 16, "gl": "angle", "scratch_drive": "C:",
                    "peak_ram_gb": 12.4, "peak_vram_mb": 1450.0,
                },
                "invariants": inv,
            }
        ])
        self.assertIn("gate4_sim", md)
        self.assertIn("h264_nvenc", md)
        self.assertIn("**PASS**", md)

    def test_master_loudness_headroom_edge_cases_and_one_pass_fallback(self):
        from src.audio.mastering import master_loudness

        captured_measure_tps = []
        captured_filters = []

        def fake_measure(inp, ti, ttp, tlra):
            captured_measure_tps.append(ttp)
            return {
                "input_i": "-16.0",
                "input_tp": "-2.0",
                "input_lra": "6.0",
                "input_thresh": "-26.0",
                "target_offset": "0.5",
            }

        def fake_encode(inp, out, sr, audio_filter=None):
            captured_filters.append(audio_filter)
            return subprocess.CompletedProcess(
                args=["ffmpeg"],
                returncode=0,
                stdout="",
                stderr='{"output_i": "-14.0", "output_tp": "-1.7"}',
            )

        with mock.patch("src.audio.mastering.measure_loudness", side_effect=fake_measure), \
             mock.patch("src.audio.mastering._encode_final", side_effect=fake_encode):
            # 1. target_tp = -9.0 -> kẹp ở -9.0 (không vượt biên âm của loudnorm)
            res_neg9 = master_loudness("in.mkv", "out.mp4", target_i=-14.0, target_tp=-9.0)
            self.assertIsNotNone(res_neg9)
            # 2. target_tp = 0.0 -> effective_tp = -0.2
            res_zero = master_loudness("in.mkv", "out.mp4", target_i=-14.0, target_tp=0.0)
            self.assertIsNotNone(res_zero)

        self.assertEqual(captured_measure_tps, [-9.0, -0.2])
        self.assertIn("TP=-9.0:", captured_filters[0])
        self.assertIn("TP=-0.2:", captured_filters[1])

        # 3. Chế độ 1-pass khi measure_loudness trả None vẫn áp effective_tp đúng và không có linear=true
        one_pass_filters = []

        def fake_encode_1pass(inp, out, sr, audio_filter=None):
            one_pass_filters.append(audio_filter)
            return subprocess.CompletedProcess(
                args=["ffmpeg"], returncode=0, stdout="", stderr='{"output_i": "-14.1"}'
            )

        with mock.patch("src.audio.mastering.measure_loudness", return_value=None), \
             mock.patch("src.audio.mastering._encode_final", side_effect=fake_encode_1pass):
            res_1p = master_loudness("in.mkv", "out.mp4", target_i=-14.0, target_tp=-1.5)
        self.assertIsNotNone(res_1p)
        self.assertIn("TP=-1.7:", one_pass_filters[0])
        self.assertNotIn("linear=true", one_pass_filters[0])

    def test_get_media_duration_thread_safe_and_packager_cleans_failed_wav(self):
        from concurrent.futures import ThreadPoolExecutor

        media = self.tmp / "concurrent_clip.mp4"
        media.write_bytes(b"MEDIA_CONCURRENT")

        fake_proc = subprocess.CompletedProcess(args=["ffprobe"], returncode=0, stdout="3.75\n", stderr="")
        with mock.patch("src.export.crop_utils.subprocess.run", return_value=fake_proc):
            with ThreadPoolExecutor(max_workers=8) as pool:
                vals = list(pool.map(lambda _: get_media_duration(media), range(16)))
        self.assertEqual(vals, [3.75] * 16)

        # Kiểm tra AssetPackager xử lý lỗi 1 shot mà không làm hỏng các shot còn lại và không để lại wav rỗng
        audio_f = self.tmp / "dummy.mp3"
        audio_f.write_bytes(b"FAKE")
        shots = [
            Shot(shot_id="ok_shot", kind=ShotKind.STORY, duration_frames=24, audio_file=str(audio_f)),
            Shot(shot_id="bad_shot", kind=ShotKind.STORY, duration_frames=24, audio_file=str(audio_f)),
        ]
        sb = Storyboard(chapter_id="err_pkg", title="Err Pkg", shots=shots)
        packager = AssetPackager(base_dir=self.tmp)

        def fake_ffmpeg(cmd, **kwargs):
            out_wav = Path(cmd[-1])
            if "bad_shot" in str(out_wav):
                out_wav.write_bytes(b"")  # Tạo file rỗng rồi báo lỗi
                raise subprocess.CalledProcessError(1, cmd)
            out_wav.write_bytes(b"RIFF_VALID_WAV")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        with mock.patch("src.visuals.asset_packager.subprocess.run", side_effect=fake_ffmpeg):
            out_dir = packager.export_hybrid_package(sb, "err_pkg", output_root=self.tmp / "packages", fps=24)

        self.assertTrue((out_dir / "ok_shot" / "voice.wav").exists())
        self.assertFalse((out_dir / "bad_shot" / "voice.wav").exists())

    def test_skill_md_files_are_synchronized_and_match_scratch_path(self):
        agents_skill = (ROOT / ".agents" / "skills" / "create-story-video" / "SKILL.md").read_text(encoding="utf-8")
        claude_skill = (ROOT / ".claude" / "skills" / "create-story-video" / "SKILL.md").read_text(encoding="utf-8")
        readme_text = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertEqual(agents_skill, claude_skill)
        self.assertIn(r"%LOCALAPPDATA%\CineStory\scratch", agents_skill)
        self.assertIn(r"%LOCALAPPDATA%\CineStory\scratch", readme_text)
        self.assertNotIn("CineStoryScratch", agents_skill)
        self.assertNotIn("CineStoryScratch", readme_text)


if __name__ == "__main__":
    unittest.main()
