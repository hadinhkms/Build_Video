import re
import unicodedata
from typing import Any, Dict, List, Optional


def normalize_token(tok: str) -> str:
    """Bỏ dấu câu xung quanh, chuyển chữ thường, chuẩn NFC."""
    t = unicodedata.normalize("NFC", tok)
    t = re.sub(r'^[^\w]+|[^\w]+$', '', t)
    return t.lower()


def find_keyword_highlights(
    text: str,
    keywords: List[str],
) -> List[str]:
    """Tìm các từ khóa cảm xúc xuất hiện trong câu để highlight."""
    if not text or not keywords:
        return []

    clean_text = unicodedata.normalize("NFC", text).lower()
    found = []

    for kw in keywords:
        clean_kw = unicodedata.normalize("NFC", kw.strip()).lower()
        if not clean_kw:
            continue
        # Khớp nguyên từ
        pattern = r'(?<!\w)' + re.escape(clean_kw) + r'(?!\w)'
        if re.search(pattern, clean_text):
            found.append(clean_kw)

    return sorted(list(set(found)))


def create_captions(
    words: List[Dict[str, Any]],
    shot_duration: float,
    emotion_keywords: Optional[List[str]] = None,
    max_words_per_caption: int = 6,
    max_chars_per_caption: int = 42,
    split_at_word_idx: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Tạo cụm phụ đề (captions) chuẩn điện ảnh (RULES §4):
    - Tối đa 6 từ / cụm, tối đa 42 ký tự.
    - Ưu tiên ngắt sau dấu câu (, . ! ? … :).
    - start = từ đầu cụm, end = start cụm kế tiếp (hoặc từ cuối + 0.3s).
    - highlight: các từ khóa cảm xúc.
    - Nếu có split_at_word_idx (ranh giới cắt cảnh con): BẮT BUỘC ngắt cụm tại đây.
    """
    if not words:
        return []

    emotion_keywords = emotion_keywords or []
    captions = []
    n = len(words)
    start_idx = 0

    while start_idx < n:
        # Tìm điểm kết thúc cụm hợp lý từ start_idx
        end_idx = min(start_idx + max_words_per_caption, n)

        # Nếu có điểm cắt cảnh con nằm trong khoảng này, bắt buộc ngắt tại đó
        if split_at_word_idx is not None and start_idx <= split_at_word_idx < end_idx:
            end_idx = split_at_word_idx + 1

        # Cắt ngắn nếu vượt quá max_chars_per_caption
        while end_idx > start_idx + 1:
            phrase = " ".join(words[i]["text"] for i in range(start_idx, end_idx))
            if len(phrase) <= max_chars_per_caption:
                break
            end_idx -= 1

        # Ưu tiên ngắt sau dấu câu nếu có dấu câu ở gần cuối cụm
        punct_idx = None
        for i in range(start_idx, end_idx):
            w_text = words[i]["text"]
            if re.search(r'[,;:.\u2026?!]|\.\.\.', w_text):
                punct_idx = i

        if punct_idx is not None and punct_idx > start_idx and (end_idx - punct_idx) <= 2:
            # Ngắt ngay sau dấu câu
            end_idx = punct_idx + 1

        # Tránh ngắt giữa chừng cụm từ khóa cảm xúc
        for kw in emotion_keywords:
            kw_tokens = kw.strip().split()
            if len(kw_tokens) > 1:
                k_len = len(kw_tokens)
                for offset in range(1, k_len):
                    check_start = end_idx - offset
                    check_end = check_start + k_len
                    if 0 <= check_start < end_idx < check_end <= n:
                        candidate_phrase = " ".join(normalize_token(words[i]["text"]) for i in range(check_start, check_end))
                        clean_kw = " ".join(normalize_token(t) for t in kw_tokens)
                        if candidate_phrase == clean_kw and check_start > start_idx:
                            end_idx = check_start
                            break

        # Tạo caption
        phrase_words = words[start_idx:end_idx]
        caption_text = " ".join(w["text"] for w in phrase_words)
        cap_start = phrase_words[0]["start"]

        # Tìm highlight keywords
        highlights = find_keyword_highlights(caption_text, emotion_keywords)

        captions.append({
            "text": caption_text,
            "start": round(cap_start, 4),
            "end": round(phrase_words[-1]["end"] + 0.3, 4),
            "highlight": highlights,
            "_end_word_idx": end_idx - 1,
        })

        start_idx = end_idx

    # Cập nhật end của mỗi cụm bằng start của cụm kế tiếp
    for i in range(len(captions) - 1):
        captions[i]["end"] = captions[i + 1]["start"]

    # Cụm cuối cùng: clamp không vượt quá shot_duration
    if captions:
        last_cap = captions[-1]
        last_cap["end"] = min(shot_duration, last_cap["end"])
        if last_cap["end"] < last_cap["start"]:
            last_cap["end"] = last_cap["start"] + 0.1

    # Dọn dẹp trường tạm
    for cap in captions:
        cap.pop("_end_word_idx", None)

    return captions
