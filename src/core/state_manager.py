import json
import os
from pathlib import Path
from typing import Optional
from src.core.models import Storyboard, Shot, ShotStatus

class StateManager:
    def __init__(self, state_file_path: str = "output/pipeline_state.json"):
        self.state_file_path = state_file_path
        os.makedirs(os.path.dirname(state_file_path), exist_ok=True)

    def save_state(self, storyboard: Storyboard) -> None:
        """Lưu toàn bộ trạng thái storyboard vào file JSON để checkpoint."""
        with open(self.state_file_path, "w", encoding="utf-8") as f:
            f.write(storyboard.model_dump_json(indent=2))

    def load_state(self) -> Optional[Storyboard]:
        """Tải trạng thái đã checkpoint từ trước nếu có."""
        if not os.path.exists(self.state_file_path):
            return None
        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Storyboard.model_validate(data)
        except Exception as e:
            print(f"[Cảnh báo] Lỗi khi đọc file state: {e}")
            return None

    def update_shot_status(self, shot_id: str, status: ShotStatus, **kwargs) -> bool:
        """Cập nhật trạng thái và thuộc tính của 1 shot cụ thể."""
        storyboard = self.load_state()
        if not storyboard:
            return False
        
        updated = False
        for shot in storyboard.shots:
            if shot.shot_id == shot_id:
                shot.status = status
                for k, v in kwargs.items():
                    if hasattr(shot, k):
                        setattr(shot, k, v)
                updated = True
                break
        
        if updated:
            self.save_state(storyboard)
        return updated
