def parse_rate_percent(rate_str: str) -> int:
    """'+5%' -> 5, '-5%' -> -5, '0%' -> 0."""
    if not rate_str:
        return 0
    clean = rate_str.replace("%", "").strip()
    try:
        return int(clean)
    except ValueError:
        return 0


def format_rate_percent(val: int) -> str:
    """5 -> '+5%', -5 -> '-5%', 0 -> '+0%'."""
    if val >= 0:
        return f"+{val}%"
    return f"{val}%"


def combine_rates(base_rate: str, extra_rate: str) -> str:
    """Cộng hai tỷ lệ phần trăm tốc độ đọc: '-5%' + '+5%' = '+0%'."""
    v1 = parse_rate_percent(base_rate)
    v2 = parse_rate_percent(extra_rate)
    return format_rate_percent(v1 + v2)
