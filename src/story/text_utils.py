import re
import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple

def normalize_text_nfc(text: str) -> str:
    """Chuẩn hóa văn bản sang dạng NFC để so khớp tiếng Việt chính xác."""
    return unicodedata.normalize("NFC", text)

def slugify_chapter_id(filename_or_title: str) -> str:
    """Tạo chapter_id: bỏ đuôi .txt, bỏ .annotated, bỏ dấu tiếng Việt, chỉ giữ [a-z0-9_]."""
    name = Path(filename_or_title).stem
    name = re.sub(r'\.annotated$', '', name, flags=re.IGNORECASE)
    # Bỏ dấu tiếng Việt
    nfkd = unicodedata.normalize("NFKD", name)
    no_accent = "".join([c for c in nfkd if not unicodedata.combining(c)])
    no_accent = no_accent.replace("đ", "d").replace("Đ", "D")
    slug = re.sub(r'[^a-zA-Z0-9]+', '_', no_accent).strip('_').lower()
    return slug or "chapter_01"

def count_syllables(text: str) -> int:
    """Đếm số âm tiết tiếng Việt (mỗi từ cách nhau bằng khoảng trắng là 1 âm tiết)."""
    words = re.findall(r'\b\w+\b', text)
    return max(1, len(words))

def split_sentences(raw_text: str) -> List[str]:
    """
    Chia câu theo dòng hoặc dấu chấm câu kết thúc (. ! ?), giữ nguyên dấu câu.
    Không cắt tại dấu '...' hoặc '…' giữa câu.
    Bỏ qua dòng không có chữ/số.
    """
    parts = re.split(r'\n+|(?<=[.!?])(?<!\.\.)\s+', raw_text)
    return [s.strip() for s in parts if s and re.search(r'\w', s)]

def extract_chapter_title_and_clean_text(text: str, user_title: Optional[str] = None) -> Tuple[str, str]:
    """
    Trích xuất tiêu đề chương theo thứ tự ưu tiên:
    1. Tham số user_title
    2. Dòng đầu dạng 'Chương N: ...' (dòng này bị bỏ khỏi nội dung kể)
    3. Fallback: 'Chương truyện điện ảnh'
    """
    lines = text.strip().splitlines()
    detected_title = None
    cleaned_lines = []

    first_line_checked = False
    for line in lines:
        line_str = line.strip()
        if not first_line_checked and line_str:
            first_line_checked = True
            m = re.match(r'^(Chương\s+\d+[\s:.\-].*)$', line_str, flags=re.IGNORECASE)
            if m:
                detected_title = m.group(1).strip()
                continue
        cleaned_lines.append(line)

    final_title = user_title or detected_title or "Chương truyện điện ảnh"
    return final_title, "\n".join(cleaned_lines)
