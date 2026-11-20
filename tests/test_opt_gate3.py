import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from src.core.hardware_profile import HardwareProfile
from src.core.models import Shot, ShotKind, Storyboard
from src.core.scratch_manager import ScratchManager
from src.core.state_manager import StateManager
from src.export.visual_builder import build_shot_visuals
from src.packaging.youtube import YouTubePackager
from src.pipeline.context import PipelineContext
from src.pipeline.stage_video_master import run_stage_video
from src.render.encoder_probe import EncoderCapability
from src.render.remotion_runner import RemotionRunner
from src.visuals.asset_check import AssetChecker
from src.visuals.stills_generator import StillsGenerator


class TestOptGate3Acceptance(unittest.TestCase):
    """Kiểm thử nghiệm thu OPT Phase 3 (Gate 3): cấm CSS nặng, VRAM/Canvas/Grain, Asset Proxy, Batch Stills & Cache 64 GB."""

    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self.remotion_src = self.root / "remotion" / "src"
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_gate3_1_static_scan_forbids_backdrop_filter_blur_and_drop_shadow_in_tsx(self):
        """Quét tĩnh toàn bộ remotion/src/**/*.tsx: 0 lần xuất hiện backdrop-*, blur-[, drop-shadow."""
        forbidden = [
            "backdrop-blur",
            "backdrop-brightness",
            "backdrop-filter",
            "blur-[",
            "drop-shadow",
        ]
        tsx_files = sorted(self.remotion_src.rglob("*.tsx"))
        self.assertGreater(len(tsx_files), 0)

        violations = []
        for fpath in tsx_files:
            content = fpath.read_text(encoding="utf-8")
            for pat in forbidden:
                if pat in content:
                    violations.append(f"{fpath.relative_to(self.root)} contains {pat!r}")

        self.assertEqual(violations, [], f"Phát hiện CSS filter nặng bị cấm:\n" + "\n".join(violations))

    def test_gate3_2_remotion_components_implement_gpu_and_canvas_optimizations(self):
        # 1. BackgroundPlate: filter & contain trên wrapper 1920x1080, KHÔNG nằm trên innerWidthPercent
        bg_src = (self.remotion_src / "components" / "BackgroundPlate.tsx").read_text(encoding="utf-8")
        self.assertIn('contain: "layout style"', bg_src)
        self.assertIn("filter: cssFilter", bg_src)
        # Xác nhận block innerWidthPercent không còn chứa thuộc tính filter
        inner_block = re.search(r"width:\s*`\$\{innerWidthPercent\}%`[\s\S]{0,240}\}\}", bg_src)
        self.assertIsNotNone(inner_block)
        self.assertNotIn("filter:", inner_block.group(0))

        # 2. AtmosphericEffects: useMemo 180 giọt mưa + chỉ 1 lần ctx.stroke() (không nằm trong vòng for)
        atm_src = (self.remotion_src / "components" / "AtmosphericEffects.tsx").read_text(encoding="utf-8")
        self.assertIn("useMemo", atm_src)
        self.assertEqual(atm_src.count("ctx.stroke()"), 1)
        self.assertIn("clearRect(", atm_src)

        # 3. FilmGrain: lớp quá khổ calc(100% + 256px) + translate3d + willChange:"transform", không dùng backgroundPosition
        grain_src = (self.remotion_src / "components" / "FilmGrain.tsx").read_text(encoding="utf-8")
        self.assertIn("calc(100% + 256px)", grain_src)
        self.assertIn("translate3d(", grain_src)
        self.assertIn('willChange: "transform"', grain_src)
        self.assertNotIn("backgroundPosition", grain_src)

        # 4. SubtitleBox: text-shadow + useMemo cho highlight
        sub_src = (self.remotion_src / "components" / "SubtitleBox.tsx").read_text(encoding="utf-8")
        self.assertIn("[text-shadow:0_2px_8px_rgba(245,158,11,0.6)]", sub_src)
        self.assertIn("useMemo", sub_src)

        # 5. EndScreen & TitleCard
        end_src = (self.remotion_src / "scenes" / "EndScreen.tsx").read_text(encoding="utf-8")
        self.assertIn("bg-black/45", end_src)
        title_src = (self.remotion_src / "scenes" / "TitleCard.tsx").read_text(encoding="utf-8")
        self.assertIn("opacity-30", title_src)
        self.assertIn("grayscale-[40%]", title_src)

    def test_gate3_3_settings_and_remotion_runner_expose_64gb_cache_flags(self):
        settings = json.loads((self.root / "config" / "settings.json").read_text(encoding="utf-8"))
        render = settings.get("render", {})
        self.assertIn("media_cache_mb", render)
        self.assertIn("offthread_video_cache_mb", render)
        self.assertIn("offthread_video_threads", render)
        self.assertEqual(render["image_format"], "jpeg")
        self.assertEqual(render["jpeg_quality"], 85)

        runner = RemotionRunner(project_root=self.root)
        cmd = runner.build_command(
            props_path=self.tmp_dir / "props.json",
            output_path=self.tmp_dir / "out.mkv",
            concurrency=16,
            crf=18,
            image_format="jpeg",
            jpeg_quality=85,
            media_cache_bytes=2 * 1024 ** 3,
            offthread_video_cache_bytes=1024 ** 3,
            offthread_video_threads=4,
        )
        self.assertEqual(cmd[cmd.index("--media-cache-bytes") + 1], str(2 * 1024 ** 3))
        self.assertEqual(cmd[cmd.index("--offthread-video-cache-bytes") + 1], str(1024 ** 3))
        self.assertEqual(cmd[cmd.index("--offthread-video-threads") + 1], "4")

    def test_gate3_4_stage_video_scales_remotion_cache_by_available_ram(self):
        chapter_dir = self.tmp_dir / "output" / "ram_ch"
        audio_dir = chapter_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        (chapter_dir / "render_props.json").write_text(
            json.dumps({"chapterId": "ram_ch", "scenes": [{"durationInFrames": 240}]}),
            encoding="utf-8",
        )
        scratch_dir = self.tmp_dir / "scratch_ram"

        def run_for_ram(ram_gb: float):
            hw = HardwareProfile(
                cpu_name="Xeon",
                cpu_physical_cores=28,
                cpu_logical_threads=56,
                cpu_sockets=2,
                numa_nodes=2,
                ram_total_gb=ram_gb,
                ram_available_gb=ram_gb * 0.7,
                has_nvidia=True,
                gpu_name="GTX 1650",
                vram_mb=4096,
                gpu_driver="610.88",
                workspace_path=str(self.root),
                workspace_drive="D:",
                workspace_disk_type="USB",
                workspace_disk_detail="USB",
                workspace_free_gb=500.0,
                localappdata_path=str(scratch_dir),
                localappdata_drive="C:",
                localappdata_disk_type="NVMe",
                localappdata_disk_detail="NVMe",
                localappdata_free_gb=200.0,
            )
            scratch_mgr = ScratchManager(
                project_root=self.root,
                scratch_dir_setting=str(scratch_dir),
                hardware_profile=hw,
            )
            ctx = PipelineContext(
                chapter_file="input/sample_chapter.txt",
                output_name="final.mp4",
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
                        "encoder": "auto",
                        "concurrency": 16,
                        "gl": "angle",
                        "crf": 18,
                        "media_cache_mb": 2048,
                        "offthread_video_cache_mb": 1024,
                        "offthread_video_threads": 4,
                    },
                },
                story_rules={},
                fps=24,
                shot_min=4.0,
                shot_max=6.5,
                split_min=2.5,
                chapter_id="ram_ch",
                chapter_dir=chapter_dir,
                audio_dir=audio_dir,
                storyboard_path=chapter_dir / "storyboard.json",
                state_mgr=StateManager(str(chapter_dir / "storyboard.json")),
                hardware_profile=hw,
                scratch_manager=scratch_mgr,
            )
            cap = EncoderCapability(
                selected_encoder="h264_nvenc",
                requested_encoder="auto",
                nvenc_available=True,
                supports_bframes=True,
                ffmpeg_bin_dir=Path("C:/ffmpeg/bin"),
                max_parallel_nvenc=3,
            )
            seen = {}

            def fake_render(self_r, **kwargs):
                seen.update(kwargs)
                self_r.last_timing = {"bundle_ms": 50, "select_ms": 300, "render_ms": 3000}
                return True

            with patch("src.pipeline.stage_video_master.probe_encoder_capability", return_value=cap), \
                 patch.object(RemotionRunner, "render", autospec=True, side_effect=fake_render):
                ok = run_stage_video(ctx)
            self.assertTrue(ok)
            return seen

        seen_64g = run_for_ram(64.0)
        self.assertEqual(seen_64g["media_cache_bytes"], 2048 * 1024 * 1024)
        self.assertEqual(seen_64g["offthread_video_cache_bytes"], 1024 * 1024 * 1024)
        self.assertEqual(seen_64g["offthread_video_threads"], 4)

        seen_8g = run_for_ram(8.0)
        self.assertLessEqual(seen_8g["media_cache_bytes"], 850 * 1024 * 1024)
        self.assertLessEqual(seen_8g["offthread_video_cache_bytes"], 450 * 1024 * 1024)

    def test_gate3_5_stills_generator_and_youtube_packager_use_render_stills_ts(self):
        props_path = self.tmp_dir / "render_props.json"
        props_path.write_text(
            json.dumps(
                {
                    "chapterId": "batch_ch",
                    "scenes": [
                        {"id": "s1", "durationInFrames": 60},
                        {"id": "s2", "durationInFrames": 100},
                        {"id": "s3", "durationInFrames": 80},
                    ],
                }
            ),
            encoding="utf-8",
        )
        out_dir = self.tmp_dir / "stills"
        scratch_dir = self.tmp_dir / "scratch"

        seen_stills_cmds = []

        def fake_stills_run(cmd, **kwargs):
            seen_stills_cmds.append(cmd)
            out_dir.mkdir(parents=True, exist_ok=True)
            for name in ("s1_f30.png", "s2_f110.png", "s3_f200.png"):
                (out_dir / name).write_bytes(b"PNG")
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="BUNDLE_CACHE hit=1 hash=abc sync_ms=5 synced_files=0\nSTILL_SUMMARY count=3/3 bundle_ms=20 select_ms=100 render_ms=500 total_ms=620\n",
                stderr="",
            )

        gen = StillsGenerator(project_root=self.root)
        with patch("src.visuals.stills_generator.subprocess.run", side_effect=fake_stills_run):
            paths = gen.render_scene_stills(
                props_path=props_path,
                output_stills_dir=out_dir,
                scratch_dir=scratch_dir,
                chapter_id="batch_ch",
                gl="angle",
                concurrency=6,
            )

        # Chỉ gọi 1 tiến trình render_stills.ts duy nhất cho cả 3 cảnh!
        self.assertEqual(len(seen_stills_cmds), 1)
        cmd = seen_stills_cmds[0]
        self.assertIn("scripts/render_stills.ts", cmd)
        self.assertIn("--all-scenes", cmd)
        self.assertEqual(cmd[cmd.index("--concurrency") + 1], "6")
        self.assertEqual(cmd[cmd.index("--chapter-id") + 1], "batch_ch")
        self.assertEqual([p.name for p in paths], ["s1_f30.png", "s2_f110.png", "s3_f200.png"])

        # YouTubePackager.export_thumbnail_base gọi render_stills.ts --frame 30 rồi ffmpeg scale 1280:720
        thumb_out = self.tmp_dir / "thumbnail_base.png"
        yt_cmds = []

        def fake_yt_run(cmd, **kwargs):
            yt_cmds.append(cmd)
            if "scripts/render_stills.ts" in cmd:
                out_arg = Path(cmd[cmd.index("--out") + 1])
                out_arg.parent.mkdir(parents=True, exist_ok=True)
                out_arg.write_bytes(b"RAW_1080P_PNG")
            else:
                Path(cmd[-1]).write_bytes(b"SCALED_720P_PNG")
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

        packager = YouTubePackager(project_root=self.root)
        with patch("src.packaging.youtube.subprocess.run", side_effect=fake_yt_run):
            ok_thumb = packager.export_thumbnail_base(
                props_path=props_path,
                output_image_path=thumb_out,
                scratch_dir=scratch_dir,
                chapter_id="batch_ch",
                gl="angle",
            )

        self.assertTrue(ok_thumb)
        self.assertEqual(len(yt_cmds), 2)
        self.assertIn("scripts/render_stills.ts", yt_cmds[0])
        self.assertEqual(yt_cmds[0][yt_cmds[0].index("--frame") + 1], "30")
        self.assertIn("scale=1280:720:flags=lanczos", yt_cmds[1])
        self.assertTrue(thumb_out.exists())

    def test_gate3_6_visual_builder_optimizes_4k_plate_cutout_and_full_image(self):
        fake_root = self.tmp_dir / "proj"
        pub_chapter = fake_root / "remotion" / "public" / "chapters" / "opt3_ch"
        (fake_root / "assets" / "environments" / "phong_khach").mkdir(parents=True, exist_ok=True)
        (fake_root / "assets" / "characters" / "nam").mkdir(parents=True, exist_ok=True)
        (fake_root / "assets" / "images").mkdir(parents=True, exist_ok=True)

        plate_4k = fake_root / "assets" / "environments" / "phong_khach" / "plate.jpg"
        Image.new("RGB", (3840, 2160), color=(70, 80, 90)).save(plate_4k, format="JPEG", quality=92)

        cutout_3k = fake_root / "assets" / "characters" / "nam" / "cutout.png"
        Image.new("RGBA", (1200, 2880), color=(150, 120, 100, 200)).save(cutout_3k, format="PNG")

        full_4k = fake_root / "assets" / "images" / "shot_02.jpg"
        Image.new("RGB", (3840, 2160), color=(30, 40, 50)).save(full_4k, format="JPEG", quality=92)

        sb = Storyboard(
            chapter_id="opt3_ch",
            title="Test",
            shots=[
                Shot(
                    shot_id="shot_01",
                    kind=ShotKind.STORY,
                    raw_text="A",
                    voice_text="A",
                    duration=4.0,
                    duration_frames=96,
                    environment_id="phong_khach",
                    on_screen_character_id="nam",
                    shot_type="medium",
                ),
                Shot(
                    shot_id="shot_02",
                    kind=ShotKind.STORY,
                    raw_text="B",
                    voice_text="B",
                    duration=4.0,
                    duration_frames=96,
                    environment_id="phong_khach",
                    shot_type="wide",
                ),
            ],
        )
        visual_modes = {
            "shot_01": {
                "mode": "layered",
                "plate_path": str(plate_4k),
                "character_path": str(cutout_3k),
            },
            "shot_02": {
                "mode": "full_image",
                "image_path": str(full_4k),
            },
        }
        checker = AssetChecker(base_dir=fake_root, config_dir=fake_root / "config")
        build_shot_visuals(
            storyboard=sb,
            visual_modes=visual_modes,
            environments={"phong_khach": {}},
            root=fake_root,
            pub_chapter_dir=pub_chapter,
            chapter_id="opt3_ch",
            fps=24,
            asset_checker=checker,
        )

        staged_plate = pub_chapter / "environments" / "phong_khach" / "plate.jpg"
        staged_cutout = pub_chapter / "characters" / "nam" / "cutout.png"
        staged_full = pub_chapter / "images" / "shot_02.jpg"

        with Image.open(staged_plate) as p_img:
            self.assertEqual(p_img.size, (2560, 1440))
        with Image.open(staged_cutout) as c_img:
            self.assertEqual(c_img.size, (800, 1920))
            self.assertEqual(c_img.mode, "RGBA")
        with Image.open(staged_full) as f_img:
            self.assertEqual(f_img.size, (2304, 1296))


if __name__ == "__main__":
    unittest.main()
