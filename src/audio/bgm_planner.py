import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.models import Ambience, Bgm, ShotKind, Storyboard


def db_to_linear(db: float) -> float:
    """Đổi từ dB sang biên độ tuyến tính: 10^(dB/20)."""
    return round(math.pow(10.0, db / 20.0), 4)


def plan_ambience_tracks(
    storyboard: Storyboard,
    environments: Dict[str, Any],
    rules: Dict[str, Any],
    foley_dir: Path,
    select_file_stable_fn,
    fps: int = 24,
) -> List[Ambience]:
    """Lập kế hoạch Ambience liền mạch theo bối cảnh."""
    ambience_list: List[Ambience] = []
    ambience_rules = rules.get("ambience", [])

    timeline_cursor = 0.0
    shot_timings = []
    for s in storyboard.shots:
        dur = s.duration_frames / fps
        shot_timings.append((s, timeline_cursor, timeline_cursor + dur))
        timeline_cursor += dur

    current_env = None
    group_start = 0.0
    group_end = 0.0

    groups: List[Tuple[str, float, float]] = []
    for s, t_start, t_end in shot_timings:
        env_id = s.environment_id or "default"
        if env_id != current_env:
            if current_env is not None:
                groups.append((current_env, group_start, group_end))
            current_env = env_id
            group_start = t_start
            group_end = t_end
        else:
            group_end = t_end

    if current_env is not None:
        groups.append((current_env, group_start, group_end))

    for env_id, g_start, g_end in groups:
        env_data = environments.get(env_id, {})
        weather_desc = env_data.get("weather", "").lower()

        for rule in ambience_rules:
            pat = rule["env_weather_pattern"]
            if re.search(r'(?<!\w)(' + pat + r')(?!\w)', weather_desc, flags=re.IGNORECASE):
                cat = rule["category"]
                vol_db = rule.get("volume_db", -20)
                fade = rule.get("fade_sec", 1.5)

                cat_dir = foley_dir / cat
                chosen_file = select_file_stable_fn(cat_dir, f"{env_id}_{cat}")
                if chosen_file:
                    rel_src = f"audio/foley/{cat}/{chosen_file}"
                    ambience_list.append(
                        Ambience(
                            src=rel_src,
                            start_sec=round(g_start, 4),
                            end_sec=round(g_end, 4),
                            volume=db_to_linear(vol_db),
                            fade_sec=fade,
                        )
                    )

    return ambience_list


def plan_bgm_track(
    storyboard: Storyboard,
    words_map: Dict[str, List[Dict[str, Any]]],
    bgm_dir: Path,
    settings: Dict[str, Any],
    select_file_stable_fn,
    fps: int = 24,
) -> Optional[Bgm]:
    """Lập kế hoạch BGM có ducking và điểm cắt nhạc ở CLIFFHANGER."""
    first_raw = storyboard.shots[0].raw_text if storyboard.shots else ""
    bgm_tag_match = re.search(r'\[BGM:\s*([^\]]+)\]', first_raw, flags=re.IGNORECASE)

    chosen_file = None
    if bgm_tag_match:
        spec = bgm_tag_match.group(1).strip()
        if spec.lower() == "none":
            return None
        cand = bgm_dir / spec
        if cand.exists():
            chosen_file = cand.name
    else:
        cfg_src = settings.get("audio", {}).get("bgm_src", "auto")
        if cfg_src != "auto":
            cand = bgm_dir / cfg_src
            if cand.exists():
                chosen_file = cand.name
        else:
            chosen_file = select_file_stable_fn(bgm_dir, storyboard.chapter_id)

    if not chosen_file:
        return None

    rel_bgm_src = f"audio/bgm/{chosen_file}"
    levels = settings.get("audio", {}).get("levels", {})
    bgm_vol_db = levels.get("bgm_gain_db", -22.0)
    ducked_vol_db = -30.0

    duck_intervals: List[Tuple[float, float]] = []
    timeline_cursor = 0.0
    cliffhanger_start: Optional[float] = None

    for shot in storyboard.shots:
        dur = shot.duration_frames / fps
        act_val = shot.narrative_act.value if hasattr(shot.narrative_act, "value") else str(shot.narrative_act)

        if act_val == "CLIFFHANGER" and cliffhanger_start is None:
            cliffhanger_start = round(timeline_cursor, 4)

        shot_words = words_map.get(shot.shot_id, [])
        if shot.kind == ShotKind.STORY and shot_words:
            w_start = timeline_cursor + shot_words[0]["start"]
            w_end = timeline_cursor + shot_words[-1]["end"]
            duck_intervals.append((round(w_start, 4), round(w_end, 4)))

        timeline_cursor += dur

    merged_duck: List[Tuple[float, float]] = []
    for iv in duck_intervals:
        if not merged_duck:
            merged_duck.append(iv)
        else:
            prev_s, prev_e = merged_duck[-1]
            curr_s, curr_e = iv
            if curr_s - prev_e <= 0.6:
                merged_duck[-1] = (prev_s, max(prev_e, curr_e))
            else:
                merged_duck.append(iv)

    return Bgm(
        src=rel_bgm_src,
        volume=db_to_linear(bgm_vol_db),
        ducked_volume=db_to_linear(ducked_vol_db),
        duck_intervals=merged_duck,
        cut_at_sec=cliffhanger_start,
    )
