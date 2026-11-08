import re
from typing import Literal

DIGIT_WORDS = {
    0: "không",
    1: "một",
    2: "hai",
    3: "ba",
    4: "bốn",
    5: "năm",
    6: "sáu",
    7: "bảy",
    8: "tám",
    9: "chín",
}

LARGE_UNITS_BAC = ["", "nghìn", "triệu", "tỷ"]
LARGE_UNITS_NAM = ["", "ngàn", "triệu", "tỷ"]


def read_three_digits(
    n: int,
    is_highest_group: bool,
    dialect: Literal["bac", "nam"] = "bac",
    read_four_as_tu: bool = True,
) -> str:
    """Đọc nhóm 3 chữ số (0 - 999)."""
    tram = n // 100
    chuc = (n % 100) // 10
    donvi = n % 10

    words = []
    zero_ten = "linh" if dialect == "bac" else "lẻ"

    # Hàng trăm
    if tram > 0:
        words.append(f"{DIGIT_WORDS[tram]} trăm")
    elif not is_highest_group:
        # Nhóm không đứng đầu có hàng trăm bằng 0 thì phải đọc "không trăm"
        words.append("không trăm")

    # Hàng chục & đơn vị
    if chuc > 1:
        words.append(f"{DIGIT_WORDS[chuc]} mươi")
        if donvi == 1:
            words.append("mốt")
        elif donvi == 4:
            words.append("tư" if read_four_as_tu else "bốn")
        elif donvi == 5:
            words.append("lăm")
        elif donvi > 0:
            words.append(DIGIT_WORDS[donvi])
    elif chuc == 1:
        words.append("mười")
        if donvi == 5:
            words.append("lăm")
        elif donvi > 0:
            words.append(DIGIT_WORDS[donvi])
    else:  # chuc == 0
        if donvi > 0:
            if tram > 0 or not is_highest_group:
                words.append(f"{zero_ten} {DIGIT_WORDS[donvi]}")
            else:
                words.append(DIGIT_WORDS[donvi])

    return " ".join(words)


def _read_under_one_billion(
    n: int,
    is_highest_block: bool = True,
    dialect: Literal["bac", "nam"] = "bac",
    read_four_as_tu: bool = True,
) -> str:
    """Đọc số nguyên dưới 1 tỷ (0 đến 999.999.999)."""
    if n == 0:
        return "không"

    large_units = LARGE_UNITS_BAC if dialect == "bac" else LARGE_UNITS_NAM

    groups = []
    temp = n
    while temp > 0:
        groups.append(temp % 1000)
        temp //= 1000

    num_groups = len(groups)
    result_parts = []

    for i in range(num_groups - 1, -1, -1):
        g = groups[i]
        if g == 0:
            continue

        is_highest = is_highest_block and (i == num_groups - 1)
        group_text = read_three_digits(
            g,
            is_highest_group=is_highest,
            dialect=dialect,
            read_four_as_tu=read_four_as_tu,
        )

        unit_str = large_units[i]
        if unit_str:
            result_parts.append(f"{group_text} {unit_str}")
        else:
            result_parts.append(group_text)

    return " ".join(result_parts).strip()


def read_integer(
    n: int,
    dialect: Literal["bac", "nam"] = "bac",
    read_four_as_tu: bool = True,
) -> str:
    """Đọc số nguyên tiếng Việt từ 0 đến hàng nghìn tỷ, triệu tỷ, tỷ tỷ."""
    if n == 0:
        return "không"

    if n < 0:
        return f"âm {read_integer(abs(n), dialect=dialect, read_four_as_tu=read_four_as_tu)}"

    # Xử lý các số từ 1 tỷ trở lên theo chu kỳ 10^9 ("tỷ")
    if n >= 1_000_000_000:
        upper = n // 1_000_000_000
        lower = n % 1_000_000_000
        upper_text = read_integer(upper, dialect=dialect, read_four_as_tu=read_four_as_tu)
        if lower == 0:
            return f"{upper_text} tỷ"
        lower_text = _read_under_one_billion(lower, is_highest_block=False, dialect=dialect, read_four_as_tu=read_four_as_tu)
        return f"{upper_text} tỷ {lower_text}".strip()

    return _read_under_one_billion(n, is_highest_block=True, dialect=dialect, read_four_as_tu=read_four_as_tu)


def read_phone_number_or_digits(digits_str: str) -> str:
    """Đọc chuỗi số từng chữ số một (ví dụ số điện thoại bắt đầu bằng 0, mã số)."""
    return " ".join(DIGIT_WORDS[int(d)] for d in digits_str if d.isdigit())


def read_number_token(
    num_str: str,
    dialect: Literal["bac", "nam"] = "bac",
    read_four_as_tu: bool = True,
) -> str:
    """
    Nhận diện và đọc một chuỗi số:
    - Nếu là số điện thoại (>= 8 chữ số bắt đầu bằng 0): đọc từng chữ số.
    - Nếu là số nguyên thông thường (có thể có dấu chấm ngăn hàng nghìn): đọc thành chữ.
    """
    clean = num_str.strip()
    # Kiểm tra số điện thoại (bắt đầu bằng 0, độ dài >= 8)
    digits_only = re.sub(r'\D', '', clean)
    if clean.startswith("0") and len(digits_only) >= 8 and not re.search(r'[,.]', clean):
        return read_phone_number_or_digits(digits_only)

    # Loại bỏ dấu chấm ngăn hàng nghìn nếu có
    unseparated = clean.replace(".", "")
    if unseparated.isdigit():
        return read_integer(int(unseparated), dialect=dialect, read_four_as_tu=read_four_as_tu)

    return clean
