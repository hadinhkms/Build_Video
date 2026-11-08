import difflib
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from src.text.vi_normalizer import Span


def normalize_token(tok: str) -> str:
    """Bỏ dấu câu xung quanh, chuyển chữ thường, chuẩn NFC."""
    t = unicodedata.normalize("NFC", tok)
    t = re.sub(r'^[^\w]+|[^\w]+$', '', t)
    return t.lower()


def align_word_boundaries_to_raw_text(
    raw_text: str,
    voice_text: str,
    spans: List[Span],
    wb_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Căn mốc thời gian từ các sự kiện WordBoundary (trên voice_text)
    ngược về từng từ trong raw_text.
    Trả về danh sách [{text, start, end}] tương ứng với các từ trong raw_text.
    """
    if not wb_events:
        return []

    raw_tokens = raw_text.strip().split()
    if not raw_tokens:
        return []

    # Nếu không có spans thay thế (raw_text == voice_text) và số lượng token bằng số wb_events
    if not spans and len(raw_tokens) == len(wb_events):
        result = []
        for tok, wb in zip(raw_tokens, wb_events):
            result.append({
                "text": tok,
                "start": wb["start"],
                "end": wb["end"],
            })
        return result

    # Trường hợp tổng quát:
    # 1. Tách voice_tokens từ voice_text
    voice_tokens = voice_text.strip().split()

    # 2. Căn wb_events với voice_tokens dùng SequenceMatcher
    clean_wb = [normalize_token(w["text"]) for w in wb_events]
    clean_voice = [normalize_token(v) for v in voice_tokens]

    matcher = difflib.SequenceMatcher(None, clean_voice, clean_wb)
    voice_token_to_wb: Dict[int, List[int]] = {}

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for v_idx, wb_idx in zip(range(i1, i2), range(j1, j2)):
                voice_token_to_wb.setdefault(v_idx, []).append(wb_idx)
        elif tag == 'replace':
            # Trường hợp gộp hoặc tách
            wb_indices = list(range(j1, j2))
            for v_idx in range(i1, i2):
                voice_token_to_wb.setdefault(v_idx, []).extend(wb_indices)

    # 3. Tính mốc cho từng voice_token
    voice_timings = []
    last_end = 0.0
    for v_idx in range(len(voice_tokens)):
        wb_idxs = voice_token_to_wb.get(v_idx, [])
        if wb_idxs:
            t_start = wb_events[wb_idxs[0]]["start"]
            t_end = wb_events[wb_idxs[-1]]["end"]
            last_end = t_end
        else:
            t_start = last_end
            t_end = last_end
        voice_timings.append((t_start, t_end))

    # 4. Ánh xạ vị trí ký tự từ raw_tokens sang voice_text bằng spans
    # Tìm khoảng ký tự (start_char, end_char) của từng raw_token
    raw_token_spans = []
    cursor = 0
    for tok in raw_tokens:
        pos = raw_text.find(tok, cursor)
        if pos == -1:
            pos = cursor
        raw_token_spans.append((pos, pos + len(tok)))
        cursor = pos + len(tok)

    # Tìm khoảng ký tự của từng voice_token
    voice_token_spans = []
    cursor = 0
    for tok in voice_tokens:
        pos = voice_text.find(tok, cursor)
        if pos == -1:
            pos = cursor
        voice_token_spans.append((pos, pos + len(tok)))
        cursor = pos + len(tok)

    # Ánh xạ raw_token -> voice_token
    result = []
    last_word_end = 0.0

    for r_idx, (r_start, r_end) in enumerate(raw_token_spans):
        # Kiểm tra xem raw_token này có nằm trong Span thay thế nào không
        matched_voice_idxs = []
        is_in_span = False

        for sp in spans:
            # Nếu raw_token giao nhau với sp
            if max(r_start, sp.raw_start) < min(r_end, sp.raw_end):
                is_in_span = True
                # Tìm các voice_tokens nằm trong sp.voice_start..sp.voice_end
                for v_idx, (v_start, v_end) in enumerate(voice_token_spans):
                    if max(v_start, sp.voice_start) < min(v_end, sp.voice_end):
                        matched_voice_idxs.append(v_idx)
                break

        if not is_in_span:
            # Đoạn giữ nguyên: tìm voice_token có vị trí ký tự tương ứng
            # Tính offset giữa raw và voice trước vị trí này
            # Tìm voice_token có cùng text hoặc gần nhất
            clean_r = normalize_token(raw_tokens[r_idx])
            best_v = None
            for v_idx, v_tok in enumerate(voice_tokens):
                if normalize_token(v_tok) == clean_r:
                    # Chọn voice_token chưa bị ghép hoặc gần vị trí tỷ lệ
                    best_v = v_idx
            if best_v is not None:
                matched_voice_idxs.append(best_v)

        if matched_voice_idxs:
            t_start = min(voice_timings[v][0] for v in matched_voice_idxs)
            t_end = max(voice_timings[v][1] for v in matched_voice_idxs)
            # Đảm bảo không giảm dần
            t_start = max(last_word_end, t_start)
            t_end = max(t_start, t_end)
            last_word_end = t_end
        else:
            t_start = last_word_end
            t_end = last_word_end

        result.append({
            "text": raw_tokens[r_idx],
            "start": round(t_start, 4),
            "end": round(t_end, 4),
        })

    # Đảm bảo mốc thời gian không giảm dần
    cur = 0.0
    for w in result:
        if w["start"] < cur:
            w["start"] = cur
        if w["end"] < w["start"]:
            w["end"] = w["start"]
        cur = w["end"]

    return result


from src.text.captions import create_captions, find_keyword_highlights

__all__ = [
    "normalize_token",
    "align_word_boundaries_to_raw_text",
    "find_keyword_highlights",
    "create_captions",
]

