from typing import Callable, List, Optional
from src.core.models import ShotKind, Storyboard


def downgrade_over_shoulder_shots(
    storyboard: Storyboard,
    has_custom_image_fn: Optional[Callable[[str, Optional[str]], bool]] = None,
) -> List[str]:
    """Hạ cấp cỡ cảnh over_shoulder theo quy tắc raccord.
    
    Quy tắc:
    - Chọn phần tử đầu tiên trong [medium, closeup, wide] khác cỡ cảnh của cả
      cảnh story liền trước lẫn liền sau.
    - Cỡ cảnh của cảnh liền trước là giá trị sau khi đã hạ cấp.
    - Ví dụ: medium -> over_shoulder -> medium hạ thành medium -> closeup -> medium.
    """
    downgraded_log = []
    story_shots = [s for s in storyboard.shots if s.kind == ShotKind.STORY]
    candidates = ["medium", "closeup", "wide"]

    for i, shot in enumerate(story_shots):
        st_val = shot.shot_type.value if hasattr(shot.shot_type, "value") else str(shot.shot_type)
        if st_val != "over_shoulder":
            continue

        if has_custom_image_fn and has_custom_image_fn(shot.shot_id, shot.parent_id):
            continue

        prev_type = None
        if i > 0:
            p_st = story_shots[i - 1].shot_type
            prev_type = p_st.value if hasattr(p_st, "value") else str(p_st)

        next_type = None
        if i + 1 < len(story_shots):
            n_st = story_shots[i + 1].shot_type
            next_type = n_st.value if hasattr(n_st, "value") else str(n_st)

        chosen_type = None
        for cand in candidates:
            if cand != prev_type and cand != next_type:
                chosen_type = cand
                break

        if chosen_type is None:
            for cand in candidates:
                if cand != prev_type:
                    chosen_type = cand
                    break

        chosen_type = chosen_type or "medium"
        old_type = shot.shot_type
        old_val = old_type.value if hasattr(old_type, "value") else str(old_type)
        shot.shot_type = chosen_type
        msg = f"Cảnh {shot.shot_id}: hạ cấp {old_val} -> {chosen_type} (tránh trùng liền kề)"
        downgraded_log.append(msg)

    return downgraded_log
