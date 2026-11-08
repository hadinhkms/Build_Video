import json
import unittest
from pathlib import Path

from src.core.models import RenderProps
from src.export.srt import build_srt_from_props, format_srt_time


class TestSrtExport(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = Path(__file__).resolve().parent / "fixtures" / "sample_chapter"
        self.sample_props_path = Path(__file__).resolve().parent.parent / "output" / "sample_chapter" / "render_props.json"

    def test_format_srt_time(self):
        self.assertEqual(format_srt_time(0.0), "00:00:00,000")
        self.assertEqual(format_srt_time(1.234), "00:00:01,234")
        self.assertEqual(format_srt_time(65.5), "00:01:05,500")
        self.assertEqual(format_srt_time(3600.0), "01:00:00,000")

    def test_build_srt_from_sample_props(self):
        if not self.sample_props_path.exists():
            self.skipTest("sample_chapter render_props.json not found")

        with open(self.sample_props_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        srt_content = build_srt_from_props(data)
        self.assertTrue(len(srt_content) > 0)

        lines = [line.strip() for line in srt_content.strip().split("\n") if line.strip()]
        # Kiểm tra cấu trúc SRT cơ bản
        self.assertEqual(lines[0], "1")
        self.assertIn("-->", lines[1])

        # Đảm bảo mốc thời gian bắt đầu từ 0 hoặc sau title card
        first_time_range = lines[1].split("-->")
        start_str = first_time_range[0].strip()
        self.assertTrue(start_str.startswith("00:00:"))


if __name__ == "__main__":
    unittest.main()
