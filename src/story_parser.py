import json
import re
from typing import Dict, List, Optional, Tuple

from src.core.models import Storyboard
from src.story.prompt_builder import (
    build_prompt_with_raccord as _build_prompt_with_raccord,
    score_tension as _score_tension,
)
from src.story.shot_builder import (
    assign_camera_and_shot_types,
    assign_narrative_acts,
    assign_on_screen_characters,
    build_initial_shots,
    insert_structural_shots,
)
from src.story.text_utils import (
    count_syllables as _count_syllables,
    extract_chapter_title_and_clean_text as _extract_chapter_title_and_clean_text,
    normalize_text_nfc,
    slugify_chapter_id,
    split_sentences as _split_sentences,
)

__all__ = [
    "normalize_text_nfc",
    "slugify_chapter_id",
    "StoryParser",
]

class StoryParser:
    def __init__(
        self,
        char_path: str = "config/characters.json",
        env_path: str = "config/environments.json",
        settings_path: str = "config/settings.json",
        rules_path: str = "config/story_rules.json",
    ):
        with open(char_path, "r", encoding="utf-8") as f:
            self.characters = json.load(f).get("characters", {})
        with open(env_path, "r", encoding="utf-8") as f:
            self.environments = json.load(f).get("environments", {})
        with open(settings_path, "r", encoding="utf-8") as f:
            self.settings = json.load(f)
        with open(rules_path, "r", encoding="utf-8") as f:
            self.rules = json.load(f)

        self.char_name_to_key = {}
        for key, char_data in self.characters.items():
            name = char_data.get("name", "").strip().lower()
            if name:
                self.char_name_to_key[normalize_text_nfc(name)] = key

    @staticmethod
    def count_syllables(text: str) -> int:
        return _count_syllables(text)

    @staticmethod
    def split_sentences(raw_text: str) -> List[str]:
        return _split_sentences(raw_text)

    def score_tension(self, text: str) -> int:
        return _score_tension(text, self.rules)

    def build_prompt_with_raccord(
        self,
        shot_type: str,
        action: str,
        character_id: str = "nhan_vat_chinh",
        env_id: str = "phong_khach_dem_mua",
    ) -> str:
        return _build_prompt_with_raccord(
            shot_type, action, character_id, env_id, self.characters, self.environments
        )

    def extract_chapter_title_and_clean_text(
        self, text: str, user_title: Optional[str] = None
    ) -> Tuple[str, str]:
        return _extract_chapter_title_and_clean_text(text, user_title)

    def _parse_lines_to_units(self, content: str, default_env: str) -> List[Dict]:
        current_env = default_env
        parsed_units = []

        for line_raw in content.splitlines():
            line = line_raw.strip()
            if not line or re.match(r'^\[(BGM|EMO):\s*[^\]]+\]', line, flags=re.IGNORECASE):
                continue

            env_match = re.match(r'^\[ENV:\s*([^\]]+)\]$', line, flags=re.IGNORECASE)
            if env_match:
                env_key = env_match.group(1).strip()
                if env_key not in self.environments:
                    raise ValueError(f"Khóa bối cảnh '[ENV: {env_key}]' không tồn tại trong config/environments.json")
                current_env = env_key
                continue

            for sentence in self.split_sentences(line):
                s = sentence.strip()
                if not s:
                    continue

                is_hook = False
                on_screen_char = None
                forced_speaker = None
                is_dialogue = False

                if re.search(r'\[HOOK\]', s, flags=re.IGNORECASE):
                    is_hook = True
                    s = re.sub(r'\[HOOK\]', '', s, flags=re.IGNORECASE).strip()

                on_match = re.search(r'\[ON:\s*([^\]]+)\]', s, flags=re.IGNORECASE)
                if on_match:
                    on_val = on_match.group(1).strip()
                    s = re.sub(r'\[ON:\s*[^\]]+\]', '', s, flags=re.IGNORECASE).strip()
                    if on_val.lower() == "none":
                        on_screen_char = "none"
                    else:
                        norm_on = normalize_text_nfc(on_val.lower())
                        on_screen_char = self.char_name_to_key.get(norm_on)

                char_tag_match = re.match(r'^\[([^\]]+)\]:\s*(.*)$', s)
                if char_tag_match:
                    tag_name = char_tag_match.group(1).strip()
                    s = char_tag_match.group(2).strip()
                    is_dialogue = True
                    norm_tag = normalize_text_nfc(tag_name.lower())
                    forced_speaker = self.char_name_to_key.get(norm_tag, "narrator")

                s = re.sub(r'\[(SFX|BGM|EMO):\s*[^\]]+\]', '', s, flags=re.IGNORECASE).strip()
                s = re.sub(r'\[[^\]]+\]', '', s).strip()

                if not is_dialogue:
                    if (s.startswith("“") and s.endswith("”")) or (s.startswith('"') and s.endswith('"')) or s.startswith("—") or s.startswith("- "):
                        is_dialogue = True
                    elif ":" in s and any(name in s.split(":")[0].lower() for name in self.char_name_to_key.keys()):
                        is_dialogue = True

                speaker = "narrator"
                if forced_speaker:
                    speaker = forced_speaker
                elif is_dialogue:
                    for name_norm, char_k in self.char_name_to_key.items():
                        if name_norm in normalize_text_nfc(s).lower():
                            speaker = char_k
                            break

                parsed_units.append({
                    "raw_text": s,
                    "voice_text": s,
                    "is_dialogue": is_dialogue,
                    "speaker": speaker,
                    "on_screen_char": on_screen_char,
                    "environment_id": current_env,
                    "is_explicit_hook": is_hook,
                    "tension_score": self.score_tension(s),
                    "syllables": self.count_syllables(s),
                })
        return parsed_units

    def parse_chapter_to_storyboard(
        self,
        raw_text: str,
        title: Optional[str] = None,
        default_env: Optional[str] = None,
        chapter_filename: str = "sample_chapter.txt",
    ) -> Storyboard:
        fps = self.settings.get("video", {}).get("fps", 24)
        visuals_cfg = self.settings.get("visuals", {})
        title_card_sec = visuals_cfg.get("title_card_sec", 2.5)
        end_screen_sec = visuals_cfg.get("end_screen_sec", 10.0)

        chapter_title, content = self.extract_chapter_title_and_clean_text(raw_text, title)
        chapter_id = slugify_chapter_id(chapter_filename)

        current_env = default_env or list(self.environments.keys())[0]
        if current_env not in self.environments:
            raise ValueError(f"Bối cảnh mặc định '{current_env}' không tồn tại trong config/environments.json")

        parsed_units = self._parse_lines_to_units(content, current_env)
        if not parsed_units:
            return Storyboard(chapter_id=chapter_id, title=chapter_title, shots=[], total_duration=0.0)

        story_shots, is_cold_open = build_initial_shots(parsed_units)
        assign_narrative_acts(story_shots, is_cold_open)
        assign_on_screen_characters(story_shots, self.char_name_to_key)
        assign_camera_and_shot_types(
            story_shots,
            self.rules,
            lambda st, act, cid, eid: self.build_prompt_with_raccord(st, act, cid, eid),
        )

        final_shots = insert_structural_shots(
            story_shots, chapter_title, fps, title_card_sec, end_screen_sec
        )

        return Storyboard(
            chapter_id=chapter_id,
            title=chapter_title,
            shots=final_shots,
            total_duration=sum(s.duration for s in final_shots),
        )
