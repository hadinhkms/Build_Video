import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, NamedTuple, Optional, Tuple

from src.text.vi_constants import ROMAN_NUMERALS, UNITS_DICT, NormalizedText, Span
from src.text.vi_numbers import read_integer, read_number_token


class VietnameseNormalizer:
    def __init__(
        self,
        pronunciations_path: Optional[str] = "config/pronunciations.json",
        dialect: Literal["bac", "nam"] = "bac",
    ):
        self.dialect = dialect
        self.pronunciations = {}
        if pronunciations_path and os.path.exists(pronunciations_path):
            with open(pronunciations_path, "r", encoding="utf-8") as f:
                self.pronunciations = json.load(f)

    def normalize(self, text: str) -> NormalizedText:
        raw_text = unicodedata.normalize("NFC", text)
        working_text = raw_text

        # Chúng ta áp dụng từng quy tắc thay thế và theo dõi vị trí thay đổi (spans)
        # Để đảm bảo tính chính xác của spans, mỗi bước thay thế cập nhật text và tính lại spans mapping
        # Hoặc dùng một pipeline step-by-step
        voice_text, spans = self._apply_all_rules(raw_text)

        return NormalizedText(
            raw_text=raw_text,
            voice_text=voice_text,
            spans=spans,
        )

    def _apply_all_rules(self, raw_text: str) -> Tuple[str, List[Span]]:
        """Áp dụng 15 quy tắc chuẩn hóa theo đúng thứ tự."""
        current_text = raw_text

        # 1. URL & Emoji (Loại bỏ URL và emoji)
        current_text = re.sub(r'https?://\S+|www\.\S+', '', current_text)
        current_text = re.sub(r'[\U00010000-\U0010ffff]', '', current_text)

        # 2. Tiền tệ ($5, 5$, 50k, 50.000đ, 2 triệu VNĐ)
        def repl_currency_k(m):
            n = int(m.group(1))
            val_text = read_integer(n, dialect=self.dialect)
            return f"{val_text} nghìn"
        current_text = re.sub(r'\b(\d+)k\b', repl_currency_k, current_text, flags=re.IGNORECASE)

        def repl_currency_dong(m):
            num_part = m.group(1).replace(".", "")
            val_text = read_integer(int(num_part), dialect=self.dialect)
            return f"{val_text} đồng"
        current_text = re.sub(r'\b(\d{1,3}(?:\.\d{3})+|\d+)\s*(?:đ|vnđ|vnd)\b', repl_currency_dong, current_text, flags=re.IGNORECASE)

        def repl_currency_dollar(m):
            num_part = m.group(1) or m.group(2)
            val_text = read_integer(int(num_part), dialect=self.dialect)
            return f"{val_text} đô la"
        current_text = re.sub(r'\$(\d+)|\b(\d+)\s*\$', repl_currency_dollar, current_text)

        current_text = re.sub(r'\bVNĐ\b|\bVND\b', 'đồng', current_text, flags=re.IGNORECASE)

        # 3. Phần trăm và khoảng phần trăm (10-15%, 82,7%)
        def repl_percent_range(m):
            n1 = read_integer(int(m.group(1)), dialect=self.dialect)
            n2 = read_integer(int(m.group(2)), dialect=self.dialect)
            return f"{n1} đến {n2} phần trăm"
        current_text = re.sub(r'\b(\d+)\s*[-–]\s*(\d+)\s*%', repl_percent_range, current_text)

        def repl_percent_float(m):
            whole = read_integer(int(m.group(1)), dialect=self.dialect)
            decimal_part = m.group(2)
            dec_words = " ".join(read_integer(int(d), dialect=self.dialect) for d in decimal_part)
            return f"{whole} phẩy {dec_words} phần trăm"
        current_text = re.sub(r'\b(\d+),(\d+)\s*%', repl_percent_float, current_text)

        def repl_percent_int(m):
            val = read_integer(int(m.group(1)), dialect=self.dialect)
            return f"{val} phần trăm"
        current_text = re.sub(r'\b(\d+)\s*%', repl_percent_int, current_text)

        # 4. Giờ (7h30, 7h, 19:05, 19:30)
        def repl_time_colon(m):
            h = int(m.group(1))
            minute = int(m.group(2))
            h_text = read_integer(h, dialect=self.dialect)
            if minute == 0:
                return f"{h_text} giờ"
            elif minute < 10:
                return f"{h_text} giờ không {read_integer(minute, dialect=self.dialect)} phút"
            else:
                return f"{h_text} giờ {read_integer(minute, dialect=self.dialect)} phút"
        current_text = re.sub(r'\b(\d{1,2}):(\d{2})\b', repl_time_colon, current_text)

        def repl_time_h(m):
            h = int(m.group(1))
            minute_str = m.group(2)
            h_text = read_integer(h, dialect=self.dialect)
            if not minute_str:
                return f"{h_text} giờ"
            minute = int(minute_str)
            if minute < 10 and len(minute_str) == 2:
                return f"{h_text} giờ không {read_integer(minute, dialect=self.dialect)}"
            return f"{h_text} giờ {read_integer(minute, dialect=self.dialect)}"
        current_text = re.sub(r'\b(\d{1,2})h(\d{1,2})?\b', repl_time_h, current_text, flags=re.IGNORECASE)

        # 5. Ngày tháng (ngày 10/5/2024, 10/5/2024, ngày 5/10)
        def repl_full_date(m):
            d = read_integer(int(m.group(1)), dialect=self.dialect)
            month_num = int(m.group(2))
            m_text = "tư" if month_num == 4 else read_integer(month_num, dialect=self.dialect)
            y = read_integer(int(m.group(3)), dialect=self.dialect)
            return f"{d} tháng {m_text} năm {y}"
        current_text = re.sub(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', repl_full_date, current_text)

        def repl_day_month(m):
            prefix = m.group(1) or ""
            d = read_integer(int(m.group(2)), dialect=self.dialect)
            month_num = int(m.group(3))
            m_text = "tư" if month_num == 4 else read_integer(month_num, dialect=self.dialect)
            if prefix:
                return f"ngày {d} tháng {m_text}"
            return f"{d} tháng {m_text}"
        current_text = re.sub(r'(ngày\s+)?\b(\d{1,2})/(\d{1,2})\b', repl_day_month, current_text, flags=re.IGNORECASE)

        # 6. "tháng N" (tháng 4 -> tháng tư, các tháng khác đọc số thường)
        def repl_thang(m):
            num = int(m.group(1))
            if num == 4:
                return "tháng tư"
            return f"tháng {read_integer(num, dialect=self.dialect)}"
        current_text = re.sub(r'\btháng\s+(\d{1,2})\b', repl_thang, current_text, flags=re.IGNORECASE)

        # 7. "thứ N" (thứ 2 -> thứ hai, thứ 4 -> thứ tư, thứ 1 -> thứ nhất)
        def repl_thu(m):
            num = int(m.group(1))
            if num == 1:
                return "thứ nhất"
            elif num == 4:
                return "thứ tư"
            elif num == 7:
                return "thứ bảy"
            return f"thứ {read_integer(num, dialect=self.dialect)}"
        current_text = re.sub(r'\bthứ\s+([1-7])\b', repl_thu, current_text, flags=re.IGNORECASE)

        # 8. Số La Mã sau Chương / Hồi / Phần / Quyển / Tập / Bài / Thế kỷ
        def repl_roman(m):
            header = m.group(1)
            roman = m.group(2).upper()
            val = ROMAN_NUMERALS.get(roman)
            if val is not None:
                return f"{header} {read_integer(val, dialect=self.dialect)}"
            return m.group(0)
        current_text = re.sub(
            r'\b(Chương|Hồi|Phần|Quyển|Tập|Bài|Thế\s+kỷ)\s+([IVXLCDM]+)\b',
            repl_roman,
            current_text,
            flags=re.IGNORECASE,
        )

        # 8b. Số âm (-5°C, -10, -3,5)
        def repl_negative_number(m):
            val_str = m.group(1)
            return f"âm {val_str}"
        current_text = re.sub(r'(?<!\S)[-–](\d+(?:,\d+)?)\b', repl_negative_number, current_text)

        # 9. Đơn vị đo (km, kg, cm, mm, m, g, ml, l, °C) khi đi sau chữ số
        def repl_units(m):
            unit_key = m.group(1)
            unit_word = UNITS_DICT.get(unit_key.lower(), UNITS_DICT.get(unit_key, unit_key))
            return f" {unit_word}"
        current_text = re.sub(r'(?<=\d)\s*(km|kg|cm|mm|ml|°C|°c|°)\b', repl_units, current_text)

        # 10. Thập phân dùng dấu phẩy (3,5 km -> ba phẩy năm ki lô mét)
        def repl_decimal_comma(m):
            whole = read_integer(int(m.group(1)), dialect=self.dialect)
            dec_str = m.group(2)
            dec_words = " ".join(read_integer(int(d), dialect=self.dialect) for d in dec_str)
            return f"{whole} phẩy {dec_words}"
        current_text = re.sub(r'\b(\d+),(\d+)\b', repl_decimal_comma, current_text)

        # 11. Số có dấu chấm ngăn hàng nghìn \d{1,3}(\.\d{3})+ (ví dụ 1.500 người)
        def repl_thousands_separator(m):
            unsep = m.group(0).replace(".", "")
            return read_integer(int(unsep), dialect=self.dialect)
        current_text = re.sub(r'\b\d{1,3}(?:\.\d{3})+\b', repl_thousands_separator, current_text)

        # 12. Số phiên bản (iOS 18.2, GPT 5.5)
        def repl_version_dot(m):
            major = read_integer(int(m.group(1)), dialect=self.dialect)
            minor = read_integer(int(m.group(2)), dialect=self.dialect)
            return f"{major} chấm {minor}"
        current_text = re.sub(r'\b(\d+)\.(\d+)\b', repl_version_dot, current_text)

        # 13. Khoảng số a-b (3-4 người)
        def repl_num_range(m):
            n1 = read_integer(int(m.group(1)), dialect=self.dialect)
            n2 = read_integer(int(m.group(2)), dialect=self.dialect)
            return f"{n1} đến {n2}"
        current_text = re.sub(r'\b(\d+)\s*[-–]\s*(\d+)\b', repl_num_range, current_text)

        # 14. Viết tắt (từ pronunciations.json)
        for abbr, full in self.pronunciations.items():
            pattern = r'\b' + re.escape(abbr) + r'\b'
            current_text = re.sub(pattern, full, current_text, flags=re.IGNORECASE)

        # 15. Ký hiệu (& -> và, + -> cộng, -> -> bỏ, @ -> bỏ)
        current_text = re.sub(r'\s*&\s*', ' và ', current_text)
        current_text = re.sub(r'\s*\+\s*', ' cộng ', current_text)
        current_text = re.sub(r'\s*[-–—]>\s*|\s*→\s*', ' ', current_text)
        current_text = re.sub(r'[@#$%^~`*]', ' ', current_text)

        # 16. Các số đếm còn lại (21, 105, 2026, số điện thoại...)
        def repl_remaining_numbers(m):
            token = m.group(0)
            return read_number_token(token, dialect=self.dialect)
        current_text = re.sub(r'\b\d+\b', repl_remaining_numbers, current_text)

        # Dọn dẹp khoảng trắng thừa nhưng bảo tồn dấu câu
        current_text = re.sub(r'[ \t]+', ' ', current_text).strip()
        current_text = re.sub(r'\s+([,;:.\u2026?!])', r'\1', current_text)

        # Tính toán spans mapping giữa raw_text và current_text
        spans = self._compute_spans(raw_text, current_text)

        return current_text, spans

    def _compute_spans(self, raw: str, voice: str) -> List[Span]:
        """
        Tính toán danh sách Span mapping các đoạn khác biệt giữa raw và voice.
        Dùng difflib.SequenceMatcher để bắt các block thay đổi.
        """
        import difflib
        matcher = difflib.SequenceMatcher(None, raw, voice)
        spans: List[Span] = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != 'equal':
                spans.append(Span(raw_start=i1, raw_end=i2, voice_start=j1, voice_end=j2))

        return spans
