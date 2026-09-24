import json
import os
import re

class StoryParser:
    def __init__(self, char_path="config/characters.json", env_path="config/environments.json", settings_path="config/settings.json"):
        with open(char_path, "r", encoding="utf-8") as f:
            self.characters = json.load(f).get("characters", {})
        with open(env_path, "r", encoding="utf-8") as f:
            self.environments = json.load(f).get("environments", {})
        with open(settings_path, "r", encoding="utf-8") as f:
            self.settings = json.load(f)

    def build_prompt_with_raccord(self, shot_type: str, action: str, character_id: str = "nhan_vat_chinh", env_id: str = "phong_khach_dem_mua") -> str:
        """Ghép prompt tuân thủ cấu trúc 5 tầng chuẩn raccord điện ảnh."""
        char = self.characters.get(character_id, {})
        env = self.environments.get(env_id, {})
        
        char_dna = char.get("dna_prompt", "")
        char_wardrobe = char.get("fixed_wardrobe", "")
        env_lighting = env.get("lighting", "")
        env_camera = env.get("camera_profile", "")
        anchors = env.get("spatial_anchors", {})

        prompt_parts = [
            f"Cinematic {shot_type}",
            f"{action}",
            f"The character is a {char_dna}, wearing {char_wardrobe}",
            f"Environment context: {anchors.get('center', '')}, {anchors.get('left', '')}, {anchors.get('right', '')}, background {anchors.get('background', '')}",
            f"Lighting: {env_lighting}",
            f"{env_camera}"
        ]
        return ", ".join(prompt_parts)

    def parse_chapter_to_storyboard(self, raw_text: str, default_char="nhan_vat_chinh", default_env="phong_khach_dem_mua") -> list:
        """
        Chia nhỏ văn bản chương truyện thành các shot 4-6 giây.
        Áp dụng quy tắc Hook đầu video, luân chuyển góc máy, và chuyển động camera.
        """
        # Chia theo câu hoặc ngắt đoạn
        sentences = [s.strip() for s in re.split(r'[.\n]+', raw_text) if s.strip()]
        if not sentences:
            return []

        storyboard = []
        shot_types = ["wide establishing shot", "medium shot", "tight close-up shot", "over-the-shoulder medium shot"]
        camera_motions = ["zoom_in", "pan_left", "zoom_out", "pan_right"]

        # 1. Tạo Shot 00: Hook giữ chân 15s đầu
        hook_text = sentences[0]
        storyboard.append({
            "shot_id": "shot_00_hook",
            "narrative_act": "HOOK",
            "voiceover": hook_text,
            "shot_type": "intense tight close-up shot",
            "action": "eyes filled with shock and suspicion, frozen in tense stillness",
            "character_id": default_char,
            "environment_id": default_env,
            "camera_motion": "rapid_zoom_in",
            "sfx_cue": "heartbeat_suspense.mp3",
            "prompt": self.build_prompt_with_raccord("intense tight close-up shot", "eyes filled with shock, frozen in silence", default_char, default_env)
        })

        # 2. Tạo các cảnh tiếp nối theo 4 hồi
        for idx, sentence in enumerate(sentences[1:], start=1):
            shot_type = shot_types[(idx - 1) % len(shot_types)]
            motion = camera_motions[(idx - 1) % len(camera_motions)]
            act = "SETUP" if idx <= 2 else ("RISING" if idx <= 5 else "CLIMAX")

            storyboard.append({
                "shot_id": f"shot_{idx:02d}",
                "narrative_act": act,
                "voiceover": sentence,
                "shot_type": shot_type,
                "action": f"narrating scene: {sentence[:40]}...",
                "character_id": default_char,
                "environment_id": default_env,
                "camera_motion": motion,
                "sfx_cue": "rain_foley.mp3" if idx % 2 == 0 else "",
                "prompt": self.build_prompt_with_raccord(shot_type, f"experiencing this moment: {sentence[:30]}", default_char, default_env)
            })

        return storyboard
