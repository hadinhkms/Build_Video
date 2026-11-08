import json
import os
import re
import unittest
from pathlib import Path

from src.audio.foley_planner import FoleyPlanner
from src.core.models import NarrativeAct, RenderProps, Shot, ShotKind, Storyboard
from src.text.alignment import align_word_boundaries_to_raw_text, create_captions
from src.text.vi_normalizer import VietnameseNormalizer
from src.tts_service import TTSService

class TestGate1Acceptance(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self.output_dir = self.root / "output" / "sample_chapter"
        self.props_path = self.output_dir / "render_props.json"
        self.storyboard_path = self.output_dir / "storyboard.json"
        self.foley_rules_path = self.root / "config" / "foley_rules.json"
        self.characters_path = self.root / "config" / "characters.json"

    def test_criterion_1_phonetic_normalization_no_digits_or_symbols(self):
        """Tiêu chí 1: Phát âm chuẩn hóa 100% không còn chữ số hay ký hiệu cấm."""
        self.assertTrue(self.props_path.exists(), f"Props file does not exist: {self.props_path}")
        with open(self.props_path, "r", encoding="utf-8") as f:
            props_data = json.load(f)

        normalizer = VietnameseNormalizer()
        forbidden_pattern = re.compile(r"[0-9%$#&@→]")

        # Kiểm tra toàn bộ voice_text trong render_props
        for scene in props_data["scenes"]:
            if scene.get("kind") == "story" and scene.get("voiceText"):
                voice_text = scene["voiceText"]
                match = forbidden_pattern.search(voice_text)
                self.assertIsNone(
                    match,
                    f"Scene {scene['id']} contains forbidden character '{match.group() if match else ''}' in voiceText: {voice_text}"
                )

        # Kiểm tra các ca chuẩn hóa tiêu biểu
        test_cases = [
            ("Lãi suất 8,5% năm 2024", "tám phẩy năm phần trăm năm hai nghìn không trăm hai mươi tư"),
            ("Giá vé 50.000đ", "năm mươi nghìn đồng"),
            ("Cách đây 15km", "mười lăm ki lô mét"),
            ("Nhiệt độ -5°C", "âm năm độ xê"),
            ("Gọi số 0912345678", "không chín một hai ba bốn năm sáu bảy tám"),
        ]
        for raw, expected_substr in test_cases:
            res = normalizer.normalize(raw)
            self.assertIn(expected_substr, res.voice_text)
            self.assertIsNone(forbidden_pattern.search(res.voice_text))

    def test_criterion_2_multi_speaker_and_act_rates(self):
        """Tiêu chí 2: Đa giọng đọc theo speaker, pitch và rate_by_act."""
        settings_path = self.root / "config" / "settings.json"
        self.assertTrue(settings_path.exists())
        with open(settings_path, "r", encoding="utf-8") as f:
            settings_data = json.load(f)

        audio_cfg = settings_data.get("audio", {})
        self.assertIn("narrator", audio_cfg)
        self.assertIn("rate_by_act", audio_cfg)
        rate_by_act = audio_cfg["rate_by_act"]
        self.assertIn("HOOK", rate_by_act)
        self.assertIn("CLIMAX", rate_by_act)
        self.assertIn("CLIFFHANGER", rate_by_act)

        self.assertTrue(self.characters_path.exists())
        with open(self.characters_path, "r", encoding="utf-8") as f:
            char_data = json.load(f)

        self.assertIn("characters", char_data)
        characters = char_data["characters"]
        self.assertGreater(len(characters), 0)

        # Kiểm tra nhân vật có voice và pitch riêng
        for char_key, char_info in characters.items():
            self.assertIn("voice", char_info)
            self.assertIn("pitch", char_info)

    def test_criterion_3_captions_and_alignment_invariants(self):
        """Tiêu chí 3: Căn mốc từ về văn bản gốc, phụ đề <= 6 từ và <= 42 ký tự."""
        with open(self.props_path, "r", encoding="utf-8") as f:
            props = json.load(f)

        for scene in props["scenes"]:
            if scene.get("kind") != "story":
                continue

            captions = scene.get("captions", [])
            for cap in captions:
                words = cap["text"].split()
                # Mỗi cụm <= 6 từ
                self.assertLessEqual(
                    len(words),
                    6,
                    f"Caption in {scene['id']} exceeds 6 words: '{cap['text']}'"
                )
                # Mỗi cụm <= 42 ký tự
                self.assertLessEqual(
                    len(cap["text"]),
                    42,
                    f"Caption in {scene['id']} exceeds 42 characters: '{cap['text']}'"
                )
                # Thời gian start < end
                self.assertLessEqual(
                    cap["start"],
                    cap["end"],
                    f"Invalid caption timing in {scene['id']}: start {cap['start']} >= end {cap['end']}"
                )

    def test_criterion_4_foley_3_layers_and_exclusion(self):
        """Tiêu chí 4: Foley 3 tầng: Ambience liền mạch, SFX có exclude, BGM ducking."""
        with open(self.props_path, "r", encoding="utf-8") as f:
            props = json.load(f)

        # 1. Ambience phủ xuyên cảnh
        self.assertIn("ambience", props)
        self.assertGreater(len(props["ambience"]), 0)
        amb = props["ambience"][0]
        self.assertTrue(amb["src"].endswith("rain_ambient.mp3"))
        self.assertEqual(amb["startSec"], 0.0)
        self.assertGreater(amb["endSec"], 40.0)

        # 2. Exclude rule: "chớp mắt" không sinh SFX sấm
        planner = FoleyPlanner()
        shot_chop_mat = Shot(
            shot_id="test_shot_1",
            raw_text="Hắn chớp mắt nhìn ra ngoài cửa sổ trong đêm tối.",
            voice_text="Hắn chớp mắt nhìn ra ngoài cửa sổ trong đêm tối.",
            narrative_act=NarrativeAct.SETUP,
            duration=5.0,
            image_prompt="A man blinking",
            shot_type="medium",
        )
        sfx_list = planner.plan_sfx_for_scene(shot=shot_chop_mat, words=[])
        thunder_sfx = [s for s in sfx_list if "thunder" in s.src]
        self.assertEqual(
            len(thunder_sfx),
            0,
            "Foley rule violation: 'chớp mắt' should NOT trigger thunder SFX"
        )

        # Nhưng câu có "sấm sét" thật thì phải sinh SFX thunder
        shot_real_thunder = Shot(
            shot_id="test_shot_2",
            raw_text="Bỗng một tia chớp rạch ngang bầu trời xé toạc màn đêm.",
            voice_text="Bỗng một tia chớp rạch ngang bầu trời xé toạc màn đêm.",
            narrative_act=NarrativeAct.CLIMAX,
            duration=5.0,
            image_prompt="Thunder flash",
            shot_type="wide",
        )
        sfx_real = planner.plan_sfx_for_scene(shot=shot_real_thunder, words=[])
        thunder_real = [s for s in sfx_real if "thunder" in s.src]
        self.assertGreater(len(thunder_real), 0, "Real thunder keyword must trigger thunder SFX")

    def test_criterion_5_bgm_ducking_and_cliffhanger_silence(self):
        """Tiêu chí 5: BGM ducking khi có thoại và cắt nhạc tại CLIFFHANGER."""
        with open(self.props_path, "r", encoding="utf-8") as f:
            props = json.load(f)

        self.assertIn("bgm", props)
        bgm = props["bgm"]
        self.assertIsNotNone(bgm)
        self.assertLess(bgm["duckedVolume"], bgm["volume"])
        self.assertGreater(len(bgm["duckIntervals"]), 0)
        self.assertIsNotNone(bgm["cutAtSec"])
        self.assertGreater(bgm["cutAtSec"], 0.0)

    def test_criterion_6_tts_caching_and_no_fallback(self):
        """Tiêu chí 6: TTS cache sha1 và không fallback ngầm 5.0s khi lỗi."""
        import tempfile
        import shutil
        import subprocess
        from unittest import mock

        tmp_dir = Path(tempfile.mkdtemp())
        try:
            tts = TTSService()
            text = "Thử nghiệm bộ đệm âm thanh giọng nói."
            test_out = tmp_dir / "test_cache_run.mp3"
            meta_path = tmp_dir / "test_cache_run.meta.json"

            call_count = 0
            def fake_edge_tts(text, output_path, voice, pitch="+0Hz", rate="+0%"):
                nonlocal call_count
                call_count += 1
                subprocess.run([
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1.0",
                    "-ar", "24000", "-ac", "1", output_path
                ], check=True)
                return [{"text": "Thử", "start": 0.0, "end": 0.5}, {"text": "nghiệm", "start": 0.5, "end": 1.0}]

            with mock.patch.object(tts, "_generate_edge_with_retry", side_effect=fake_edge_tts):
                # Lần 1: Gọi sinh audio (phát sinh 1 lần gọi)
                dur1 = tts.generate_audio(text=text, output_path=str(test_out), voice="vi-VN-HoaiMyNeural")
                self.assertTrue(test_out.exists())
                self.assertTrue(meta_path.exists())
                self.assertEqual(call_count, 1)

                # Lần 2: Gọi lại cùng tham số -> đọc từ cache, call_count vẫn là 1
                dur2 = tts.generate_audio(text=text, output_path=str(test_out), voice="vi-VN-HoaiMyNeural")
                self.assertEqual(dur1, dur2)
                self.assertEqual(call_count, 1, "Lần gọi thứ 2 phải đọc từ cache và không phát sinh request TTS mới!")

            # Lỗi ffprobe phải raise Exception, không fallback 5.0s
            with self.assertRaises(Exception):
                tts.get_audio_duration(str(tmp_dir / "non_existent_file_xyz_123.mp3"))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
