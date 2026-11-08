import json
import os
import subprocess
import unittest
from pathlib import Path

from src.core.models import NarrativeAct, RenderProps, ShotKind, Storyboard

class TestGate0Acceptance(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self.output_dir = self.root / "output" / "sample_chapter"
        self.props_path = self.output_dir / "render_props.json"
        self.storyboard_path = self.output_dir / "storyboard.json"
        self.video_path = self.output_dir / "video.remotion.mp4"

    def test_gate0_data_contract(self):
        self.assertTrue(self.props_path.exists(), f"Props file does not exist: {self.props_path}")
        with open(self.props_path, "r", encoding="utf-8") as f:
            content = f.read()
        props = RenderProps.model_validate_json(content, by_name=False)
        self.assertEqual(props.schema_version, 1)
        self.assertEqual(props.chapter_id, "sample_chapter")
        self.assertGreater(len(props.scenes), 0)

    def test_gate0_script_orchestrator_invariants(self):
        self.assertTrue(self.storyboard_path.exists(), f"Storyboard does not exist: {self.storyboard_path}")
        with open(self.storyboard_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sb = Storyboard.model_validate(data)

        # 1. Có HOOK và title_card ngay sau HOOK
        hook_shots = [s for s in sb.shots if s.narrative_act == NarrativeAct.HOOK and s.kind == ShotKind.STORY]
        self.assertGreater(len(hook_shots), 0)
        title_card = next(s for s in sb.shots if s.kind == ShotKind.TITLE_CARD)
        self.assertIsNotNone(title_card)
        # title_card nằm ngay sau cảnh hook cuối cùng
        last_hook_idx = max(i for i, s in enumerate(sb.shots) if s.narrative_act == NarrativeAct.HOOK and s.kind == ShotKind.STORY)
        title_card_idx = next(i for i, s in enumerate(sb.shots) if s.kind == ShotKind.TITLE_CARD)
        self.assertEqual(title_card_idx, last_hook_idx + 1)

        # 2. Cảnh story cuối cùng là CLIFFHANGER
        story_shots = [s for s in sb.shots if s.kind == ShotKind.STORY]
        self.assertEqual(story_shots[-1].narrative_act, NarrativeAct.CLIFFHANGER)

        # 3. Có end_screen ở cuối
        self.assertEqual(sb.shots[-1].kind, ShotKind.END_SCREEN)

        # 4. Không có 2 cảnh story liền nhau cùng cỡ
        for i in range(len(story_shots) - 1):
            self.assertNotEqual(
                story_shots[i].shot_type,
                story_shots[i + 1].shot_type,
                f"Shots {story_shots[i].shot_id} and {story_shots[i+1].shot_id} have same shot_type",
            )

        # 5. Mọi cảnh story <= 6.5s và cảnh con >= 2.5s
        for s in story_shots:
            self.assertLessEqual(
                s.duration,
                6.55,
                f"Shot {s.shot_id} duration {s.duration}s exceeds 6.5s",
            )
            if s.parent_id:
                self.assertGreaterEqual(
                    s.duration,
                    2.45,
                    f"Child shot {s.shot_id} duration {s.duration}s is less than 2.5s",
                )

    def test_gate0_walking_skeleton_duration(self):
        if not self.video_path.exists():
            self.skipTest(f"Video {self.video_path} not rendered yet")

        with open(self.props_path, "r", encoding="utf-8") as f:
            props_data = json.load(f)

        total_frames = sum(s["durationInFrames"] for s in props_data["scenes"])
        fps = props_data["fps"]
        expected_dur = total_frames / fps

        # Đo thời lượng thực tế của luồng video MP4 bằng ffprobe
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(self.video_path),
        ]
        out = subprocess.check_output(cmd, text=True).strip()
        actual_dur = float(out)

        # Sai số tối đa 1 frame = 1 / fps = 0.0417s
        self.assertAlmostEqual(actual_dur, expected_dur, delta=(1.5 / fps))

    def test_gate0_child_shots_audio_continuity(self):
        """Kiểm tra tính liên tục của âm thanh tại điểm cắt giữa các cảnh con theo Gate 0."""
        self.assertTrue(self.storyboard_path.exists())
        with open(self.storyboard_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sb = Storyboard.model_validate(data)

        # Gom các cảnh con theo parent_id
        children_by_parent = {}
        for s in sb.shots:
            if s.parent_id:
                children_by_parent.setdefault(s.parent_id, []).append(s)

        self.assertGreater(len(children_by_parent), 0, "Phải có ít nhất 1 cảnh được tách hình")

        for parent_id, child_shots in children_by_parent.items():
            # Cảnh con đầu tiên phải có offset = 0
            self.assertEqual(child_shots[0].audio_start_in_file_sec, 0.0)

            # Các cảnh con kế tiếp phải có offset đúng bằng tổng frame trước đó / fps
            cum_frames = child_shots[0].duration_frames
            for cs in child_shots[1:]:
                expected_offset = cum_frames / 24.0
                self.assertAlmostEqual(
                    cs.audio_start_in_file_sec,
                    expected_offset,
                    delta=1.5 / 24.0,
                    msg=f"Audio offset of {cs.shot_id} does not match frame grid",
                )
                cum_frames += cs.duration_frames

            # Cỡ cảnh liên tiếp giữa các cảnh con phải khác nhau
            for i in range(len(child_shots) - 1):
                self.assertNotEqual(
                    child_shots[i].shot_type,
                    child_shots[i + 1].shot_type,
                    f"Child shots {child_shots[i].shot_id} and {child_shots[i+1].shot_id} must have different shot types",
                )

if __name__ == "__main__":
    unittest.main()
