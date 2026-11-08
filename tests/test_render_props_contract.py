import os
import unittest
from pathlib import Path
from src.core.models import RenderProps

class TestRenderPropsContract(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = Path(__file__).resolve().parent.parent / "remotion" / "src" / "fixtures"
        self.sample_path = self.fixtures_dir / "render_props.sample.json"
        self.invalid_dir = self.fixtures_dir / "invalid"

    def test_sample_props_valid(self):
        self.assertTrue(self.sample_path.exists(), f"Sample file not found at {self.sample_path}")
        with open(self.sample_path, "r", encoding="utf-8") as f:
            data_str = f.read()
        props = RenderProps.model_validate_json(data_str, by_name=False)
        self.assertEqual(props.schema_version, 1)
        self.assertEqual(props.chapter_id, "sample_chapter")
        self.assertGreater(len(props.scenes), 0)

    def test_all_invalid_fixtures_rejected(self):
        self.assertTrue(self.invalid_dir.exists(), f"Invalid fixtures dir not found at {self.invalid_dir}")
        invalid_files = list(self.invalid_dir.glob("*.json"))
        self.assertGreaterEqual(len(invalid_files), 8, "Must test at least 8 invalid fixtures")

        for inv_file in invalid_files:
            with self.subTest(file=inv_file.name):
                with open(inv_file, "r", encoding="utf-8") as f:
                    content = f.read()
                with self.assertRaises(Exception, msg=f"Pydantic accepted invalid fixture: {inv_file.name}"):
                    RenderProps.model_validate_json(content, by_name=False)

if __name__ == "__main__":
    unittest.main()
