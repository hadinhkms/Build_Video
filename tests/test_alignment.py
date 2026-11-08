import json
import unittest
from pathlib import Path

from src.text.alignment import (
    align_word_boundaries_to_raw_text,
    create_captions,
    find_keyword_highlights,
)
from src.text.vi_normalizer import VietnameseNormalizer


class TestAlignment(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = Path(__file__).resolve().parent / "fixtures" / "sample_chapter"
        self.normalizer = VietnameseNormalizer(pronunciations_path="config/pronunciations.json")

    def test_align_sample_chapter_frozen_fixtures(self):
        # Đọc shot_01.words.json đã đóng băng
        with open(self.fixtures_dir / "shot_01.words.json", "r", encoding="utf-8") as f:
            wb_events = json.load(f)

        raw_text = "Cơn mưa cuối tháng Mười trút xuống mái hiên rầm rập."
        res_norm = self.normalizer.normalize(raw_text)

        aligned_words = align_word_boundaries_to_raw_text(
            raw_text=raw_text,
            voice_text=res_norm.voice_text,
            spans=res_norm.spans,
            wb_events=wb_events,
        )

        self.assertEqual(len(aligned_words), len(raw_text.split()))

        # Kiểm tra tính đơn điệu của thời gian: start <= end và không giảm dần
        prev_end = 0.0
        for w in aligned_words:
            self.assertLessEqual(w["start"], w["end"])
            self.assertGreaterEqual(w["start"], prev_end - 0.05)
            prev_end = w["end"]

    def test_align_with_number_expansion(self):
        # Câu có số: "Chào năm 2026 tới."
        raw_text = "Chào năm 2026 tới."
        norm = self.normalizer.normalize(raw_text)
        # voice_text: "Chào năm hai nghìn không trăm hai mươi sáu tới."

        # Giả lập wb_events cho voice_text
        voice_tokens = norm.voice_text.split()
        wb_events = []
        cur_t = 0.1
        for vt in voice_tokens:
            wb_events.append({"text": vt, "start": round(cur_t, 2), "end": round(cur_t + 0.25, 2)})
            cur_t += 0.3

        aligned_words = align_word_boundaries_to_raw_text(
            raw_text=raw_text,
            voice_text=norm.voice_text,
            spans=norm.spans,
            wb_events=wb_events,
        )

        # Số từ trong raw_text là 4: "Chào", "năm", "2026", "tới."
        self.assertEqual(len(aligned_words), 4)
        self.assertEqual(aligned_words[2]["text"], "2026")

        # Từ 2026 phải bao trọn các âm tiết từ "hai" đến "sáu"
        # "hai" là token thứ 2 (start = 0.7), "sáu" là token thứ 9 (end = 3.05)
        self.assertLessEqual(aligned_words[2]["start"], aligned_words[2]["end"])
        self.assertAlmostEqual(aligned_words[2]["start"], wb_events[2]["start"], delta=0.05)
        self.assertAlmostEqual(aligned_words[2]["end"], wb_events[8]["end"], delta=0.05)

    def test_captions_constraints(self):
        # Tạo danh sách từ mẫu dài 15 từ
        words = []
        text = "Ánh đèn vàng từ cây đèn góc phòng hắt lên nửa khuôn mặt trầm mặc của anh, để lộ vết sẹo."
        raw_tokens = text.split()
        for i, tok in enumerate(raw_tokens):
            words.append({"text": tok, "start": round(i * 0.4, 2), "end": round(i * 0.4 + 0.35, 2)})

        captions = create_captions(
            words=words,
            shot_duration=7.5,
            emotion_keywords=["khuôn mặt", "vết sẹo"],
            max_words_per_caption=6,
            max_chars_per_caption=42,
        )

        self.assertGreater(len(captions), 1)

        for cap in captions:
            # Tối đa 6 từ
            self.assertLessEqual(len(cap["text"].split()), 6)
            # Tối đa 42 ký tự
            self.assertLessEqual(len(cap["text"]), 42)
            # start <= end
            self.assertLessEqual(cap["start"], cap["end"])

        # Tính nối tiếp: start cụm sau = end cụm trước
        for i in range(len(captions) - 1):
            self.assertAlmostEqual(captions[i]["end"], captions[i + 1]["start"], delta=0.01)

        # Highlight từ khóa cảm xúc
        all_highlights = [h for c in captions for h in c["highlight"]]
        self.assertIn("khuôn mặt", all_highlights)
        self.assertIn("vết sẹo", all_highlights)

    def test_captions_forced_split_at_boundary(self):
        words = []
        text = "Tôi ngồi đối diện mình trong phòng khách... không hề có hơi thở."
        tokens = text.split()
        for i, tok in enumerate(tokens):
            words.append({"text": tok, "start": round(i * 0.3, 2), "end": round(i * 0.3 + 0.25, 2)})

        # Giả sử điểm cắt ranh giới ở từ thứ 6 ("khách...")
        split_idx = 6

        captions = create_captions(
            words=words,
            shot_duration=6.0,
            split_at_word_idx=split_idx,
        )

        # Kiểm tra xem có cụm nào kết thúc đúng tại split_idx không
        # tức là cụm đó kết thúc bằng từ tokens[split_idx]
        found_cut_break = False
        for i, cap in enumerate(captions[:-1]):
            cap_words = cap["text"].split()
            if cap_words[-1] == tokens[split_idx]:
                found_cut_break = True
                break

        self.assertTrue(found_cut_break, "Captions must break at forced split boundary")


if __name__ == "__main__":
    unittest.main()
