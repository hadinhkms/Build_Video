from dataclasses import dataclass
from typing import List, NamedTuple


class Span(NamedTuple):
    raw_start: int
    raw_end: int
    voice_start: int
    voice_end: int


@dataclass
class NormalizedText:
    raw_text: str
    voice_text: str
    spans: List[Span]  # Các đoạn bị thay thế (raw_start, raw_end, voice_start, voice_end)


ROMAN_NUMERALS = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
    "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
    "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19, "XX": 20,
    "XXI": 21, "XXII": 22,
}

UNITS_DICT = {
    "km": "ki lô mét",
    "kg": "ki lô gam",
    "cm": "xen ti mét",
    "mm": "mi li mét",
    "m": "mét",
    "g": "gam",
    "ml": "mi li lít",
    "l": "lít",
    "°C": "độ xê",
    "°c": "độ xê",
    "°": "độ",
    "%": "phần trăm",
}
