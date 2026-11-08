from pathlib import Path
import cv2
import numpy as np


def load_cv2_image(path: Path) -> np.ndarray:
    """Đọc ảnh hỗ trợ đường dẫn Unicode trên Windows."""
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Không thể đọc ảnh: {path}")
    return img


def save_cv2_image(path: Path, img: np.ndarray) -> None:
    """Lưu ảnh hỗ trợ đường dẫn Unicode trên Windows."""
    ext = path.suffix
    success, encoded = cv2.imencode(ext, img)
    if not success:
        raise ValueError(f"Không thể mã hóa ảnh: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded.tofile(str(path))
