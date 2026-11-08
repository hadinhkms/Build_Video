import os
import unittest
from src.core.models import NarrativeAct, ShotKind
from src.story_parser import StoryParser, slugify_chapter_id

class TestStoryRules(unittest.TestCase):
    def setUp(self):
        self.parser = StoryParser()
        with open("input/sample_chapter.txt", "r", encoding="utf-8") as f:
            self.sample_text = f.read()

    def test_hook_scoring(self):
        # Câu 0: "không hề có hơi thở" (2) + "..." (2) = 4 điểm
        # Câu 5: "run rẩy" (2) = 2 điểm
        # Các câu khác = 0 điểm
        sentences = self.parser.split_sentences(self.sample_text)
        self.assertEqual(len(sentences), 7)
        self.assertEqual(self.parser.score_tension(sentences[0]), 4)
        self.assertEqual(self.parser.score_tension(sentences[1]), 0)
        self.assertEqual(self.parser.score_tension(sentences[2]), 0)
        self.assertEqual(self.parser.score_tension(sentences[3]), 0)
        self.assertEqual(self.parser.score_tension(sentences[4]), 0)
        self.assertEqual(self.parser.score_tension(sentences[5]), 2)
        self.assertEqual(self.parser.score_tension(sentences[6]), 0)

    def test_sample_chapter_storyboard_structure(self):
        sb = self.parser.parse_chapter_to_storyboard(self.sample_text, chapter_filename="sample_chapter.txt")
        self.assertEqual(sb.chapter_id, "sample_chapter")

        # Có 7 câu truyện + 1 title_card + 1 end_screen = 9 shots
        self.assertEqual(len(sb.shots), 9)

        # Hook là câu 0 dùng tại chỗ
        self.assertEqual(sb.shots[0].shot_id, "shot_00")
        self.assertEqual(sb.shots[0].narrative_act, NarrativeAct.HOOK)
        self.assertEqual(sb.shots[0].camera_motion, "rapid_zoom_in")

        # Title card nằm ngay sau hook
        self.assertEqual(sb.shots[1].shot_id, "title_card")
        self.assertEqual(sb.shots[1].kind, ShotKind.TITLE_CARD)
        self.assertEqual(sb.shots[1].camera_motion, "static")

        # Cảnh cuối cùng của truyện là CLIFFHANGER
        story_shots = [s for s in sb.shots if s.kind == ShotKind.STORY]
        self.assertEqual(story_shots[-1].shot_id, "shot_06")
        self.assertEqual(story_shots[-1].narrative_act, NarrativeAct.CLIFFHANGER)

        # End screen ở cuối
        self.assertEqual(sb.shots[-1].shot_id, "end_screen")
        self.assertEqual(sb.shots[-1].kind, ShotKind.END_SCREEN)
        self.assertEqual(sb.shots[-1].camera_motion, "static")

    def test_no_consecutive_identical_shot_types(self):
        sb = self.parser.parse_chapter_to_storyboard(self.sample_text)
        story_shots = [s for s in sb.shots if s.kind == ShotKind.STORY]
        for i in range(len(story_shots) - 1):
            self.assertNotEqual(
                story_shots[i].shot_type,
                story_shots[i + 1].shot_type,
                f"Consecutive story shots {story_shots[i].shot_id} and {story_shots[i+1].shot_id} have identical shot_type: {story_shots[i].shot_type}",
            )

    def test_cold_open_when_hook_is_later_sentence(self):
        text = (
            "Hôm nay trời đẹp.\n"
            "Tôi đi dạo quanh hồ.\n"
            "Bỗng nhiên, một bàn tay đầy máu xuất hiện... không hề có hơi thở!\n"
            "Tôi hoảng sợ quay về."
        )
        sb = self.parser.parse_chapter_to_storyboard(text, chapter_filename="test_cold.txt")
        self.assertEqual(sb.shots[0].shot_id, "shot_hook")
        self.assertEqual(sb.shots[0].narrative_act, NarrativeAct.HOOK)
        self.assertEqual(sb.shots[1].shot_id, "title_card")

        # Câu 2 gốc vẫn giữ vị trí shot_02
        shot_02 = next((s for s in sb.shots if s.shot_id == "shot_02"), None)
        self.assertIsNotNone(shot_02)
        self.assertIn("bàn tay đầy máu", shot_02.raw_text)

    def test_explicit_hook_tag(self):
        text = (
            "Câu mở đầu bình thường.\n"
            "[HOOK] Câu thứ hai được ép làm Hook dù không có từ khóa.\n"
            "Câu thứ ba đầy máu kinh hoàng."
        )
        sb = self.parser.parse_chapter_to_storyboard(text)
        self.assertEqual(sb.shots[0].shot_id, "shot_hook")
        self.assertIn("Câu thứ hai", sb.shots[0].raw_text)
        self.assertNotIn("[HOOK]", sb.shots[0].raw_text)

    def test_tags_stripping_and_dialogue(self):
        text = (
            "[BGM: bgm_night.mp3]\n"
            "[EMO: bí mật, rùng rợn]\n"
            "[ENV: phong_khach_dem_mua]\n"
            "[ON: Nam] Nam đang nhìn vào màn đêm.\n"
            "[Nam]: “Tôi không biết chuyện gì đã xảy ra.”[SFX: thunder.mp3]\n"
            "[ON: none] Căn phòng lại chìm vào im lặng."
        )
        sb = self.parser.parse_chapter_to_storyboard(text)
        story_shots = [s for s in sb.shots if s.kind == ShotKind.STORY]

        # Kiểm tra thẻ bị gỡ
        for s in story_shots:
            for tag in ["[BGM:", "[EMO:", "[ENV:", "[ON:", "[SFX:"]:
                self.assertNotIn(tag.lower(), s.raw_text.lower())
                self.assertNotIn(tag.lower(), s.voice_text.lower())

        # Shot 01 là thoại của Nam
        shot_01 = next(s for s in story_shots if s.shot_id == "shot_01")
        self.assertTrue(shot_01.is_dialogue)
        self.assertEqual(shot_01.speaker, "nhan_vat_chinh")
        self.assertNotIn("[Nam]:", shot_01.raw_text)

        # Shot 02 bị ép [ON: none] -> on_screen_character_id is None
        shot_02 = next(s for s in story_shots if s.shot_id == "shot_02")
        self.assertIsNone(shot_02.on_screen_character_id)

    def test_invalid_env_raises_error(self):
        text = "[ENV: non_existing_environment]\nCâu chuyện bắt đầu."
        with self.assertRaises(ValueError):
            self.parser.parse_chapter_to_storyboard(text)

    def test_on_screen_character_flow_on_sample_chapter(self):
        sb = self.parser.parse_chapter_to_storyboard(self.sample_text)
        story_shots = [s for s in sb.shots if s.kind == ShotKind.STORY]
        # Câu 0 và 1: None (cảnh mưa)
        self.assertIsNone(story_shots[0].on_screen_character_id)
        self.assertIsNone(story_shots[1].on_screen_character_id)
        # Câu 2: nhắc "Nam" -> nhan_vat_chinh
        self.assertEqual(story_shots[2].on_screen_character_id, "nhan_vat_chinh")
        # Câu 3 đến 6: kế thừa nhan_vat_chinh
        for s in story_shots[3:]:
            self.assertEqual(s.on_screen_character_id, "nhan_vat_chinh")

    def test_slugify_chapter_id(self):
        self.assertEqual(slugify_chapter_id("sample_chapter.annotated.txt"), "sample_chapter")
        self.assertEqual(slugify_chapter_id("chuong_1_dem_mua.txt"), "chuong_1_dem_mua")
        self.assertEqual(slugify_chapter_id("Chương 02: Bí Mật.txt"), "chuong_02_bi_mat")

if __name__ == "__main__":
    unittest.main()
