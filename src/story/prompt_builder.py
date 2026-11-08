import re
from typing import Dict
from src.story.text_utils import normalize_text_nfc

def score_tension(text: str, rules: Dict) -> int:
    """Tính điểm độ căng của câu dựa trên từ khóa, dấu câu và quy tắc story_rules.json."""
    text_norm = normalize_text_nfc(text).lower()
    score = 0
    weights = rules.get("tension_weights", {})
    kw_weight = weights.get("keyword", 2)
    ellipsis_weight = weights.get("ellipsis", 2)
    question_weight = weights.get("question", 1)
    exclamation_weight = weights.get("exclamation", 1)

    # Từ khóa căng thẳng (khớp nguyên từ)
    for kw in rules.get("tension_keywords", []):
        kw_norm = normalize_text_nfc(kw).lower()
        pattern = r'(?<!\w)' + re.escape(kw_norm) + r'(?!\w)'
        if re.search(pattern, text_norm):
            score += kw_weight

    # Dấu chấm lửng
    if "..." in text or "…" in text:
        score += ellipsis_weight
    # Dấu hỏi
    if "?" in text:
        score += question_weight
    # Dấu chấm than
    if "!" in text:
        score += exclamation_weight

    return score

def build_prompt_with_raccord(
    shot_type: str,
    action: str,
    character_id: str,
    env_id: str,
    characters: Dict,
    environments: Dict,
) -> str:
    """Ghép prompt 5 tầng chuẩn raccord."""
    char = characters.get(character_id, {})
    env = environments.get(env_id, {})
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
        f"{env_camera}",
    ]
    return ", ".join(prompt_parts)
