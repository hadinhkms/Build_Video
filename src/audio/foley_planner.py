import hashlib
import json
import math
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.models import (
    Ambience,
    Bgm,
    NarrativeAct,
    Sfx,
    Shot,
    ShotKind,
    Storyboard,
)


def db_to_linear(db: float) -> float:
    """Đổi từ dB sang biên độ tuyến tính: 10^(dB/20)."""
    return round(math.pow(10.0, db / 20.0), 4)


class FoleyPlanner:
    def __init__(
        self,
        foley_rules_path: str = "config/foley_rules.json",
        environments_path: str = "config/environments.json",
        settings_path: str = "config/settings.json",
        assets_dir: str = "assets/audio",
    ):
        self.assets_dir = Path(assets_dir)
        self.foley_dir = self.assets_dir / "foley"
        self.bgm_dir = self.assets_dir / "bgm"

        with open(foley_rules_path, "r", encoding="utf-8") as f:
            self.rules = json.load(f)
        with open(environments_path, "r", encoding="utf-8") as f:
            self.environments = json.load(f).get("environments", {})
        with open(settings_path, "r", encoding="utf-8") as f:
            self.settings = json.load(f)

    def select_file_stable(self, category_or_dir: Path, seed_id: str) -> Optional[str]:
        """Chọn 1 file audio trong thư mục bằng hash sha1 ổn định."""
        if not category_or_dir.exists():
            return None
        files = sorted([f.name for f in category_or_dir.glob("*.mp3")])
        if not files:
            return None
        idx = int(hashlib.sha1(seed_id.encode("utf-8")).hexdigest(), 16) % len(files)
        return files[idx]

    def plan_sfx_for_scene(
        self,
        shot: Shot,
        words: List[Dict[str, Any]],
        is_first_of_act: bool = False,
    ) -> List[Sfx]:
        """
        Lập kế hoạch SFX one-shot cho 1 cảnh theo thứ tự ưu tiên:
        1. Thẻ chỉ định tay [SFX: ...]
        2. Từ khóa khớp trong raw_text (trừ các trường hợp bị exclude)
        3. Mặc định theo hồi (act_defaults) nếu cảnh không có SFX từ 1 và 2
        """
        sfx_list: List[Sfx] = []
        limits = self.rules.get("limits", {})
        max_sfx = limits.get("max_oneshot_per_scene", 2)
        min_gap = limits.get("min_gap_sec", 1.5)

        # 1. Thẻ [SFX: ...]
        raw_text = shot.raw_text or ""
        sfx_tag_match = re.search(r'\[SFX:\s*([^\]]+)\]', raw_text, flags=re.IGNORECASE)
        if sfx_tag_match:
            spec = sfx_tag_match.group(1).strip().lower()
            if spec == "none":
                return []
            # Tìm file trong foley
            found_path = None
            for p in self.foley_dir.rglob(spec):
                if p.is_file():
                    found_path = p
                    break
            if found_path:
                rel_src = found_path.relative_to(self.assets_dir).as_posix()
                sfx_list.append(
                    Sfx(
                        src=f"audio/{rel_src}",
                        start_sec=0.0,
                        volume=db_to_linear(-10.0),
                        duration_sec=None,
                        fade_in_sec=0.0,
                        fade_out_sec=0.0,
                    )
                )
                return sfx_list

        # 2. Từ khóa khớp trong raw_text
        clean_text = unicodedata.normalize("NFC", raw_text).lower()

        oneshot_rules = self.rules.get("oneshot", [])
        matched_candidates = []

        for rule in oneshot_rules:
            pattern = rule["pattern"]
            exclude = rule.get("exclude")
            category = rule["category"]
            vol_db = rule.get("volume_db", -10)
            preroll = rule.get("preroll_sec", 0.0)

            # Tìm mọi match của pattern
            pat_matches = list(re.finditer(r'(?<!\w)(' + pattern + r')(?!\w)', clean_text))
            if not pat_matches:
                continue

            # Tìm mọi match của exclude
            excl_spans = []
            if exclude:
                for em in re.finditer(r'(?<!\w)(' + exclude + r')(?!\w)', clean_text):
                    excl_spans.append((em.start(), em.end()))

            for pm in pat_matches:
                p_start, p_end = pm.start(), pm.end()
                # Kiểm tra xem có overlap với exclude không
                is_excluded = False
                for e_start, e_end in excl_spans:
                    if max(p_start, e_start) < min(p_end, e_end):
                        is_excluded = True
                        break
                if is_excluded:
                    continue

                # Tìm mốc thời gian chính xác của từ tương ứng trong words
                matched_word_start = 0.0
                if words:
                    cursor = 0
                    best_w_idx = 0
                    min_dist = 999999
                    for w_i, w in enumerate(words):
                        w_clean = unicodedata.normalize("NFC", w["text"]).lower()
                        w_pos = clean_text.find(w_clean, cursor)
                        if w_pos != -1:
                            cursor = w_pos + len(w_clean)
                            dist = abs(w_pos - p_start)
                            if dist < min_dist:
                                min_dist = dist
                                best_w_idx = w_i
                            if w_pos <= p_start < cursor:
                                best_w_idx = w_i
                                break
                        else:
                            alt_pos = clean_text.find(w_clean)
                            if alt_pos != -1:
                                dist = abs(alt_pos - p_start)
                                if dist < min_dist:
                                    min_dist = dist
                                    best_w_idx = w_i
                    matched_word_start = words[best_w_idx]["start"]

                sfx_start = max(0.0, round(matched_word_start - preroll, 4))
                matched_candidates.append({
                    "category": category,
                    "vol_db": vol_db,
                    "start_sec": sfx_start,
                })

        # Sắp xếp candidate theo start_sec và lọc theo min_gap, max_sfx
        matched_candidates.sort(key=lambda x: x["start_sec"])
        last_t = -999.0

        for cand in matched_candidates:
            if len(sfx_list) >= max_sfx:
                break
            if cand["start_sec"] - last_t < min_gap:
                continue

            cat_dir = self.foley_dir / cand["category"]
            chosen_file = self.select_file_stable(cat_dir, f"{shot.shot_id}_{cand['category']}")
            if chosen_file:
                rel_src = f"audio/foley/{cand['category']}/{chosen_file}"
                sfx_list.append(
                    Sfx(
                        src=rel_src,
                        start_sec=cand["start_sec"],
                        volume=db_to_linear(cand["vol_db"]),
                        duration_sec=None,
                        fade_in_sec=0.0,
                        fade_out_sec=0.0,
                    )
                )
                last_t = cand["start_sec"]

        # 3. Mặc định theo hồi (act_defaults)
        if not sfx_list and is_first_of_act:
            act_defaults = self.rules.get("act_defaults", {})
            act_key = shot.narrative_act.value if hasattr(shot.narrative_act, "value") else str(shot.narrative_act)
            default_cat = act_defaults.get(act_key)
            if default_cat:
                cat_dir = self.foley_dir / default_cat
                chosen_file = self.select_file_stable(cat_dir, f"{shot.shot_id}_{default_cat}")
                if chosen_file:
                    rel_src = f"audio/foley/{default_cat}/{chosen_file}"
                    sfx_list.append(
                        Sfx(
                            src=rel_src,
                            start_sec=0.0,
                            volume=db_to_linear(-12.0),
                            duration_sec=None,
                            fade_in_sec=0.0,
                            fade_out_sec=0.0,
                        )
                    )

        return sfx_list

    def plan_ambience(self, storyboard: Storyboard, fps: int = 24) -> List[Ambience]:
        """Lập kế hoạch Ambience liền mạch theo bối cảnh."""
        from src.audio.bgm_planner import plan_ambience_tracks

        return plan_ambience_tracks(
            storyboard=storyboard,
            environments=self.environments,
            rules=self.rules,
            foley_dir=self.foley_dir,
            select_file_stable_fn=self.select_file_stable,
            fps=fps,
        )

    def plan_bgm(
        self,
        storyboard: Storyboard,
        words_map: Dict[str, List[Dict[str, Any]]],
        fps: int = 24,
    ) -> Optional[Bgm]:
        """Lập kế hoạch BGM có ducking và điểm cắt nhạc ở CLIFFHANGER."""
        from src.audio.bgm_planner import plan_bgm_track

        bgm = plan_bgm_track(
            storyboard=storyboard,
            words_map=words_map,
            bgm_dir=self.bgm_dir,
            settings=self.settings,
            select_file_stable_fn=self.select_file_stable,
            fps=fps,
        )
        if bgm is None:
            print("[Cảnh báo Foley] Không tìm thấy file BGM nào trong assets/audio/bgm/")
        return bgm
