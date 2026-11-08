import copy
import json
import math
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from src.core.models import NarrativeAct, Shot, ShotKind, ShotType

def normalize_nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)

def find_split_candidates(
    words: List[Dict[str, Any]],
    raw_text: str,
    total_frames: int,
    fps: int,
    shot_max_sec: float = 6.5,
    split_min_sec: float = 2.5,
    phrase_starters: Optional[List[str]] = None,
    num_parts: int = 2,
) -> Optional[Tuple[int, int]]:
    """
    Tìm điểm cắt tối ưu giữa 2 từ cho một cảnh dài:
    - Trả về (cut_word_idx, cut_frame) sao cho từ 0..cut_word_idx thuộc cảnh con 1,
      từ cut_word_idx+1..end thuộc phần còn lại.
    - Cảnh con 1 có số frame = cut_frame.
    - Bậc 0: ngay sau dấu câu (, ; : . … ...).
    - Bậc 1: ngay trước một từ mở đầu cụm (phrase_starters).
    - Bậc 2: mọi ranh giới còn lại trừ từ láy (2 âm tiết giống nhau).
    """
    if not words or len(words) < 2:
        return None

    starters_set = set(
        normalize_nfc(s.strip().lower())
        for s in (phrase_starters or ["vào", "trong", "để", "và", "nhưng", "rồi", "khi", "mà", "thì", "với", "trên", "dưới", "từ", "nơi"])
    )

    tokens = raw_text.strip().split()
    tokens_match_words = (len(tokens) == len(words))

    target_frame = total_frames / float(num_parts)
    split_min_frames = round(split_min_sec * fps)
    shot_max_frames = round(shot_max_sec * fps)
    remaining_parts = max(1, num_parts - 1)

    candidates = []

    for i in range(len(words) - 1):
        t_cut = (words[i]["end"] + words[i + 1]["start"]) / 2.0
        cut_frame = round(t_cut * fps)
        f0 = cut_frame
        f1 = total_frames - cut_frame

        # Kiểm tra điều kiện hợp lệ
        if f0 < split_min_frames or f0 > shot_max_frames:
            continue
        if f1 < remaining_parts * split_min_frames or (remaining_parts == 1 and f1 > shot_max_frames):
            continue

        w_curr = normalize_nfc(words[i]["text"].strip().lower())
        w_next = normalize_nfc(words[i + 1]["text"].strip().lower())

        # Từ láy: 2 âm tiết liên tiếp giống nhau
        is_redup = (w_curr == w_next)
        if is_redup:
            continue

        # Xác định bậc (tier)
        tier = 2
        # Bậc 0: ngay sau dấu câu
        if tokens_match_words:
            tok = tokens[i]
            if re.search(r'[,;:.\u2026]|\.\.\.', tok):
                tier = 0
        else:
            # Fallback nếu tokens lệch words: kiểm tra dấu câu ở cuối text của word
            if re.search(r'[,;:.\u2026]|\.\.\.', words[i]["text"]):
                tier = 0

        # Bậc 1: ngay trước từ mở đầu cụm
        if tier > 0:
            clean_next = re.sub(r'^[^\w]+|[^\w]+$', '', w_next)
            if clean_next in starters_set:
                tier = 1

        dist = abs(cut_frame - target_frame)
        candidates.append((tier, dist, cut_frame, i))

    if not candidates:
        return None

    # Sắp xếp theo tier tăng dần, khoảng cách tới điểm mục tiêu tăng dần
    candidates.sort(key=lambda c: (c[0], c[1]))
    best = candidates[0]
    return (best[3], best[2])


def split_long_shot(
    shot: Shot,
    words: List[Dict[str, Any]],
    fps: int,
    shot_max_sec: float = 6.5,
    split_min_sec: float = 2.5,
    phrase_starters: Optional[List[str]] = None,
) -> Tuple[List[Shot], List[List[Dict[str, Any]]]]:
    """
    Tách 1 cảnh dài thành N cảnh con (shot_id + 'a', shot_id + 'b', shot_id + 'c'...).
    N = ceil(total_frames / (shot_max_sec * fps)).
    Trả về (child_shots, child_words).
    Nếu không cần tách (duration_frames <= shot_max_frames), trả về ([shot], [words]).
    """
    shot_max_frames = round(shot_max_sec * fps)
    if shot.duration_frames <= shot_max_frames or not words:
        return [shot], [words]

    num_parts = math.ceil(shot.duration_frames / shot_max_frames)
    if num_parts <= 1:
        return [shot], [words]

    remaining_words = copy.deepcopy(words)
    remaining_text = shot.raw_text or shot.voiceover
    remaining_frames = shot.duration_frames

    segments_frames: List[int] = []
    segments_words: List[List[Dict[str, Any]]] = []
    segments_texts: List[str] = []

    rem_n = num_parts
    while rem_n > 1:
        cand = find_split_candidates(
            words=remaining_words,
            raw_text=remaining_text,
            total_frames=remaining_frames,
            fps=fps,
            shot_max_sec=shot_max_sec,
            split_min_sec=split_min_sec,
            phrase_starters=phrase_starters,
            num_parts=rem_n,
        )
        if not cand:
            cand = find_split_candidates(
                words=remaining_words,
                raw_text=remaining_text,
                total_frames=remaining_frames,
                fps=fps,
                shot_max_sec=shot_max_sec,
                split_min_sec=split_min_sec,
                phrase_starters=phrase_starters,
                num_parts=2,
            )
        if not cand:
            break

        cut_word_idx, cut_frame = cand
        f_part = cut_frame
        words_part = remaining_words[: cut_word_idx + 1]

        tokens = remaining_text.split()
        if len(tokens) == len(remaining_words):
            text_part = " ".join(tokens[: cut_word_idx + 1])
            remaining_text = " ".join(tokens[cut_word_idx + 1 :])
        else:
            text_part = " ".join(w["text"] for w in words_part)
            remaining_text = " ".join(w["text"] for w in remaining_words[cut_word_idx + 1 :])

        segments_frames.append(f_part)
        segments_words.append(words_part)
        segments_texts.append(text_part)

        remaining_frames -= f_part
        shift_sec = f_part / fps
        next_words = remaining_words[cut_word_idx + 1 :]
        for w in next_words:
            w["start"] = max(0.0, round(w["start"] - shift_sec, 4))
            w["end"] = max(w["start"], round(w["end"] - shift_sec, 4))
        remaining_words = next_words
        rem_n -= 1

    segments_frames.append(remaining_frames)
    segments_words.append(remaining_words)
    segments_texts.append(remaining_text)

    if len(segments_frames) <= 1:
        return [shot], [words]

    shot_priority_by_act = {
        NarrativeAct.HOOK: [ShotType.CLOSEUP, ShotType.EXTREME_CLOSEUP],
        NarrativeAct.SETUP: [ShotType.WIDE, ShotType.MEDIUM],
        NarrativeAct.RISING: [ShotType.MEDIUM, ShotType.OVER_SHOULDER],
        NarrativeAct.CLIMAX: [ShotType.CLOSEUP, ShotType.EXTREME_CLOSEUP],
        NarrativeAct.CLIFFHANGER: [ShotType.EXTREME_CLOSEUP, ShotType.CLOSEUP, ShotType.MEDIUM],
    }
    priorities = shot_priority_by_act.get(shot.narrative_act, [ShotType.MEDIUM, ShotType.CLOSEUP])

    child_shots: List[Shot] = []
    child_words_list: List[List[Dict[str, Any]]] = []
    curr_offset = shot.audio_start_in_file_sec
    prev_type = None

    for idx, (f_seg, w_seg, t_seg) in enumerate(zip(segments_frames, segments_words, segments_texts)):
        suffix = chr(ord('a') + idx)
        child = copy.deepcopy(shot)
        child.shot_id = f"{shot.shot_id}{suffix}"
        child.parent_id = shot.shot_id
        child.raw_text = t_seg
        child.voice_text = t_seg
        child.duration_frames = f_seg
        child.duration = round(f_seg / fps, 4)
        child.audio_start_in_file_sec = round(curr_offset, 4)

        if idx == 0:
            chosen_type = shot.shot_type
        else:
            chosen_type = priorities[0].value
            for p in priorities:
                if p.value != prev_type:
                    chosen_type = p.value
                    break
        child.shot_type = chosen_type
        prev_type = chosen_type

        if shot.narrative_act == NarrativeAct.HOOK and idx > 0:
            child.camera_motion = "zoom_in"

        child_shots.append(child)
        child_words_list.append(w_seg)
        curr_offset += f_seg / fps

    return child_shots, child_words_list
