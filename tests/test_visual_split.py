import json
import math
import os
import unittest
from pathlib import Path

from src.core.models import NarrativeAct, Shot, ShotKind
from src.visuals.visual_splitter import find_split_candidates, split_long_shot

class TestVisualSplit(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = Path(__file__).resolve().parent / "fixtures" / "sample_chapter"
        self.fps = 24
        self.shot_min = 4.0
        self.shot_max = 6.5
        self.split_min = 2.5
        self.pad = 0.6
        self.phrase_starters = [
            "vào", "trong", "để", "và", "nhưng", "rồi", "khi", "mà", "thì", "với", "trên", "dưới", "từ", "nơi"
        ]

    def _load_fixture(self, name: str):
        path = self.fixtures_dir / name
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_shot_00_split_tier_0(self):
        words = self._load_fixture("shot_00_hook.words.json")
        raw_text = "Đêm hôm đó, tôi nhận ra kẻ đang ngồi lặng lẽ đối diện mình trong phòng khách... không hề có hơi thở."
        # Audio duration từ file là 6.000s -> total = ceil((6.0 + 0.6) * 24 - 1e-6) = 159 frames
        total_frames = math.ceil((6.0 + self.pad) * self.fps - 1e-6)
        self.assertEqual(total_frames, 159)

        cand = find_split_candidates(
            words=words,
            raw_text=raw_text,
            total_frames=total_frames,
            fps=self.fps,
            shot_max_sec=self.shot_max,
            split_min_sec=self.split_min,
            phrase_starters=self.phrase_starters,
        )
        self.assertIsNotNone(cand)
        cut_word_idx, cut_frame = cand
        # Điểm cắt tại sau "khách..." (word index 16)
        self.assertEqual(cut_word_idx, 16)
        self.assertEqual(words[cut_word_idx]["text"], "khách")
        self.assertEqual(words[cut_word_idx + 1]["text"], "không")

        # Khớp bảng ở mục 3.4c: 3.94s / 2.69s (sai số <= 1 frame)
        f0 = cut_frame
        f1 = total_frames - cut_frame
        self.assertEqual(f0 + f1, total_frames)
        self.assertAlmostEqual(f0 / self.fps, 3.94, delta=1.5 / self.fps)
        self.assertAlmostEqual(f1 / self.fps, 2.69, delta=1.5 / self.fps)

    def test_shot_03_split_tier_0(self):
        words = self._load_fixture("shot_03.words.json")
        raw_text = "Ánh đèn vàng từ cây đèn góc phòng hắt lên nửa khuôn mặt trầm mặc của anh, để lộ vết sẹo mờ nơi đuôi mắt phải."
        # Audio duration là 6.744s -> total = ceil((6.744 + 0.6) * 24 - 1e-6) = 177 frames
        total_frames = math.ceil((6.744 + self.pad) * self.fps - 1e-6)
        self.assertEqual(total_frames, 177)

        cand = find_split_candidates(
            words=words,
            raw_text=raw_text,
            total_frames=total_frames,
            fps=self.fps,
            shot_max_sec=self.shot_max,
            split_min_sec=self.split_min,
            phrase_starters=self.phrase_starters,
        )
        self.assertIsNotNone(cand)
        cut_word_idx, cut_frame = cand
        # Điểm cắt tại sau "anh," (word index 16)
        self.assertEqual(cut_word_idx, 16)
        self.assertEqual(words[cut_word_idx]["text"], "anh")
        self.assertEqual(words[cut_word_idx + 1]["text"], "để")

        # Khớp bảng: 3.73s / 3.65s (sai số <= 1 frame)
        f0 = cut_frame
        f1 = total_frames - cut_frame
        self.assertEqual(f0 + f1, total_frames)
        self.assertAlmostEqual(f0 / self.fps, 3.73, delta=1.5 / self.fps)
        self.assertAlmostEqual(f1 / self.fps, 3.65, delta=1.5 / self.fps)

    def test_shot_04_split_tier_1_phrase_starter_avoid_reduplication(self):
        words = self._load_fixture("shot_04.words.json")
        raw_text = "Anh không hề chớp mắt, đôi con ngươi đen thẳm chỉ nhìn chằm chằm vào chiếc cốc trà nguội ngắt trên bàn."
        # Audio duration 5.928s -> total = ceil((5.928 + 0.6) * 24 - 1e-6) = 157 frames
        total_frames = math.ceil((5.928 + self.pad) * self.fps - 1e-6)
        self.assertEqual(total_frames, 157)

        cand = find_split_candidates(
            words=words,
            raw_text=raw_text,
            total_frames=total_frames,
            fps=self.fps,
            shot_max_sec=self.shot_max,
            split_min_sec=self.split_min,
            phrase_starters=self.phrase_starters,
        )
        self.assertIsNotNone(cand)
        cut_word_idx, cut_frame = cand
        # Điểm cắt tại sau "chằm" và trước "vào" (phrase starter "vào", tránh cắt giữa "chằm chằm")
        self.assertEqual(words[cut_word_idx]["text"], "chằm")
        self.assertEqual(words[cut_word_idx + 1]["text"], "vào")

        # Khớp bảng: 3.44s / 3.10s (sai số <= 1 frame)
        f0 = cut_frame
        f1 = total_frames - cut_frame
        self.assertEqual(f0 + f1, total_frames)
        self.assertAlmostEqual(f0 / self.fps, 3.44, delta=1.5 / self.fps)
        self.assertAlmostEqual(f1 / self.fps, 3.10, delta=1.5 / self.fps)

    def test_split_long_shot_generates_correct_child_shots(self):
        words = self._load_fixture("shot_03.words.json")
        raw_text = "Ánh đèn vàng từ cây đèn góc phòng hắt lên nửa khuôn mặt trầm mặc của anh, để lộ vết sẹo mờ nơi đuôi mắt phải."
        total_frames = math.ceil((6.744 + self.pad) * self.fps - 1e-6)

        parent_shot = Shot(
            shot_id="shot_03",
            kind=ShotKind.STORY,
            narrative_act=NarrativeAct.RISING,
            raw_text=raw_text,
            voiceover=raw_text,
            duration=round(total_frames / self.fps, 4),
            duration_frames=total_frames,
            audio_start_in_file_sec=0.0,
            shot_type="medium",
            camera_motion="zoom_in",
        )

        child_shots, child_words = split_long_shot(
            shot=parent_shot,
            words=words,
            fps=self.fps,
            shot_max_sec=self.shot_max,
            split_min_sec=self.split_min,
            phrase_starters=self.phrase_starters,
        )

        self.assertEqual(len(child_shots), 2)
        shot_a, shot_b = child_shots
        words_a, words_b = child_words

        # IDs
        self.assertEqual(shot_a.shot_id, "shot_03a")
        self.assertEqual(shot_b.shot_id, "shot_03b")
        self.assertEqual(shot_a.parent_id, "shot_03")
        self.assertEqual(shot_b.parent_id, "shot_03")

        # Frames sum
        self.assertEqual(shot_a.duration_frames + shot_b.duration_frames, total_frames)

        # startInFileSec
        self.assertEqual(shot_a.audio_start_in_file_sec, 0.0)
        self.assertEqual(shot_b.audio_start_in_file_sec, round(shot_a.duration_frames / self.fps, 4))

        # Shot types differ
        self.assertNotEqual(shot_a.shot_type, shot_b.shot_type)

        # Words timings reset for child_b
        self.assertGreaterEqual(words_b[0]["start"], 0.0)
        self.assertLess(words_b[0]["start"], words[len(words_a)]["start"])

    def test_split_very_long_shot_three_parts(self):
        # Tạo câu dài 14s (336 frames tại 24fps) -> N = ceil(336 / 156) = 3 phần
        words = []
        raw_words = [
            "Hôm", "nay", "trời", "mưa", "rất", "lớn,",
            "tôi", "ngồi", "lặng", "lẽ", "bên", "cửa", "sổ,",
            "nhìn", "chằm", "chằm", "vào", "màn", "đêm", "tối", "tăm", "ngoài", "kia."
        ]
        # Mỗi từ cách nhau 0.6s -> tổng ~13.8s + tail pad = ~14.4s -> 346 frames
        for i, w in enumerate(raw_words):
            words.append({"text": w, "start": round(i * 0.6, 2), "end": round(i * 0.6 + 0.45, 2)})

        total_frames = 346
        parent_shot = Shot(
            shot_id="shot_long",
            kind=ShotKind.STORY,
            narrative_act=NarrativeAct.RISING,
            raw_text=" ".join(raw_words),
            voiceover=" ".join(raw_words),
            duration=round(total_frames / self.fps, 4),
            duration_frames=total_frames,
            audio_start_in_file_sec=0.0,
            shot_type="medium",
            camera_motion="zoom_in",
        )

        child_shots, child_words = split_long_shot(
            shot=parent_shot,
            words=words,
            fps=self.fps,
            shot_max_sec=self.shot_max,
            split_min_sec=self.split_min,
            phrase_starters=self.phrase_starters,
        )

        self.assertEqual(len(child_shots), 3)
        self.assertEqual(child_shots[0].shot_id, "shot_longa")
        self.assertEqual(child_shots[1].shot_id, "shot_longb")
        self.assertEqual(child_shots[2].shot_id, "shot_longc")

        # Mọi cảnh con <= 6.5s và >= 2.5s
        for cs in child_shots:
            self.assertLessEqual(cs.duration, self.shot_max + 0.05)
            self.assertGreaterEqual(cs.duration, self.split_min - 0.05)

        # Tổng số frame bảo toàn
        self.assertEqual(sum(cs.duration_frames for cs in child_shots), total_frames)

        # Cỡ cảnh luân phiên
        self.assertNotEqual(child_shots[0].shot_type, child_shots[1].shot_type)
        self.assertNotEqual(child_shots[1].shot_type, child_shots[2].shot_type)

if __name__ == "__main__":
    unittest.main()
