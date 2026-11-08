import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


class AssetPackager:
    """Xuất gói prompt tạo tài sản hình ảnh thủ công (0đ) cho bối cảnh và nhân vật."""

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        base_dir: Optional[Path] = None,
    ):
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent.parent
        self.config_dir = config_dir or (self.base_dir / "config")
        self.env_path = self.config_dir / "environments.json"
        self.char_path = self.config_dir / "characters.json"

    def _load_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def export_package(self, chapter_id: str, output_root: Optional[Path] = None) -> Path:
        target_dir = (output_root or self.base_dir / "packages") / chapter_id
        target_dir.mkdir(parents=True, exist_ok=True)

        env_data = self._load_json(self.env_path).get("environments", {})
        char_data = self._load_json(self.char_path).get("characters", {})

        # 1. Xuất prompt cho từng bối cảnh (plate)
        for env_key, env_info in env_data.items():
            env_dir = target_dir / "environments" / env_key
            env_dir.mkdir(parents=True, exist_ok=True)

            anchors = env_info.get("spatial_anchors", {})
            anchor_parts = []
            for pos in ["left", "center", "right", "background"]:
                if pos in anchors:
                    anchor_parts.append(f"{pos}: {anchors[pos]}")
            anchors_str = ", ".join(anchor_parts)

            lighting = env_info.get("lighting", "")
            camera = env_info.get("camera_profile", "")
            weather = env_info.get("weather", "")

            # Bắt buộc: có đủ anchors, và có "empty room, no people" (hoặc "no people")
            prompt_lines = [
                f"Cinematic background plate for {env_info.get('name', env_key)}.",
                f"Scene layout: {anchors_str}.",
                f"Lighting: {lighting}.",
                f"Weather: {weather}.",
                f"Camera: {camera}.",
                "Requirements: empty room, no people, wide establishing composition, 16:9 aspect ratio, ultra-detailed, minimum 2560x1440 resolution.",
            ]
            plate_prompt = "\n".join([p for p in prompt_lines if p.strip()])

            prompt_file = env_dir / "plate_prompt.txt"
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(plate_prompt)

        # 2. Xuất prompt cho từng nhân vật (base)
        for char_key, char_info in char_data.items():
            char_dir = target_dir / "characters" / char_key
            char_dir.mkdir(parents=True, exist_ok=True)

            dna = char_info.get("dna_prompt", "")
            wardrobe = char_info.get("fixed_wardrobe", "")
            forbidden = char_info.get("forbidden_traits", "")
            face_ref = char_info.get("face_reference_image", "")

            char_prompt_lines = [
                f"Character portrait for {char_info.get('name', char_key)} ({char_info.get('role', '')}).",
                f"Appearance DNA: {dna}.",
                f"Wardrobe: {wardrobe}.",
                "Framing & Pose: half-body, front-facing, neutral expression, eyes open, mouth closed, plain light-grey background, soft even light.",
            ]
            if forbidden:
                char_prompt_lines.append(f"Negative / Forbidden: {forbidden}.")
            if face_ref:
                char_prompt_lines.append(f"Reference face: Use '{face_ref}' as face reference if tool supports Image-to-Image / Reference.")

            char_prompt = "\n".join([c for c in char_prompt_lines if c.strip()])
            with open(char_dir / "base_prompt.txt", "w", encoding="utf-8") as f:
                f.write(char_prompt)

        # 3. Tạo README.md hướng dẫn người dùng
        readme_content = f"""# GÓI TẠO TÀI SẢN HÌNH ẢNH 0Đ - CHƯƠNG: {chapter_id}

Tài liệu này hướng dẫn cách tạo ảnh background plate và nhân vật miễn phí chất lượng cao để video giữ tính nhất quán (raccord).

## 1. CÔNG CỤ TẠO ẢNH ĐỀ XUẤT (MIỄN PHÍ 0Đ)
- **Google ImageFX / Gemini**: Chất lượng chân dung người Việt rất tốt, không watermark.
- **Microsoft Copilot / Bing Image Creator (DALL-E 3)**: Miễn phí 15 boost/ngày, hiểu prompt tiếng Anh chi tiết.
- **SeaArt / Leonardo.ai / Krea.ai**: Hỗ trợ ControlNet và Face Reference.

---

## 2. QUY TRÌNH TẠO ẢNH PLATE BỐI CẢNH
Mỗi bối cảnh chỉ cần tạo **1 tấm duy nhất** và dùng lại cho toàn bộ chương:
1. Mở file prompt tại `environments/<env_key>/plate_prompt.txt`.
2. Copy toàn bộ nội dung prompt dán vào công cụ tạo ảnh.
3. Chọn tỉ lệ khung hình **16:9** (hoặc kích thước tối thiểu **2560x1440**).
4. Đảm bảo plate **không có người** (empty room, no people).
5. Lưu ảnh vào đường dẫn dự án:
   `assets/environments/<env_key>/plate.png` (hoặc `plate.jpg`)

---

## 3. QUY TRÌNH TẠO ẢNH NHÂN VẬT
Mỗi nhân vật chỉ cần tạo **1 ảnh gốc bán thân (half-body)**:
1. Mở file prompt tại `characters/<char_key>/base_prompt.txt`.
2. Nếu công cụ hỗ trợ Image-to-Image / Face Swap, hãy tải kèm ảnh tham chiếu `face_reference_image`.
3. Yêu cầu ảnh:
   - Chụp bán thân (từ ngực/bụng lên đến đầu), nhìn thẳng.
   - Nền xám nhạt hoặc trơn đơn sắc để script `cutout.py` tự động tách nền sạch.
   - Mắt mở tự nhiên, miệng ngậm.
4. Lưu ảnh vào đường dẫn:
   `assets/characters/<char_key>/base.png` (hoặc `base.jpg`)

---

## 4. TỰ ĐỘNG TÁCH NỀN VÀ KIỂM TRA
Sau khi bạn đã đặt các file ảnh vào thư mục `assets/`, chạy lệnh:
```powershell
python run_pipeline.py --renderer remotion --stage assets --input input/{chapter_id}.txt
```
Pipeline sẽ:
1. Tự động chạy `rembg` để tách nền các ảnh nhân vật thành `base_cutout.png`.
2. Tính toán ma trận crop và slot định vị `base_cutout.json`.
3. Kiểm tra chất lượng và cảnh báo nếu ảnh cần điều chỉnh.
"""
        with open(target_dir / "README.md", "w", encoding="utf-8") as f:
            f.write(readme_content)

        return target_dir

    def export_hybrid_package(
        self,
        storyboard: Any,
        chapter_id: str,
        output_root: Optional[Path] = None,
        fps: int = 24,
    ) -> Path:
        """Xuất gói clip hybrid (image.png, voice.wav, motion_prompt.txt, README.txt) cho từng cảnh."""
        target_dir = (output_root or self.base_dir / "packages") / chapter_id / "shots"
        target_dir.mkdir(parents=True, exist_ok=True)

        for shot in storyboard.shots:
            kind_str = str(getattr(shot, "kind", "")).lower()
            if kind_str not in ("story", "shotkind.story"):
                continue

            shot_dir = target_dir / shot.shot_id
            shot_dir.mkdir(parents=True, exist_ok=True)

            dur_sec = round(float(shot.duration_frames) / float(fps), 3)

            # 1. image.png
            target_img = shot_dir / "image.png"
            still_p = self.base_dir / "output" / chapter_id / "stills" / f"{shot.shot_id}.png"
            asset_img_p = self.base_dir / "assets" / "images" / f"{shot.shot_id}.jpg"

            if still_p.exists():
                shutil.copy2(still_p, target_img)
            elif asset_img_p.exists():
                shutil.copy2(asset_img_p, target_img)
            else:
                default_img = self.base_dir / "assets" / "characters" / "main_char_face.jpg"
                if default_img.exists():
                    shutil.copy2(default_img, target_img)

            # 2. voice.wav
            audio_f = getattr(shot, "audio_file", None)
            if audio_f:
                audio_src = Path(audio_f)
                if not audio_src.is_absolute():
                    audio_src = self.base_dir / audio_src
                if audio_src.exists():
                    start_sec = float(getattr(shot, "audio_start_in_file_sec", 0.0) or 0.0)
                    out_wav = shot_dir / "voice.wav"
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-v", "error",
                        "-ss", str(start_sec),
                        "-t", str(dur_sec),
                        "-i", str(audio_src),
                        "-ac", "1",
                        "-ar", "16000",
                        str(out_wav),
                    ]
                    try:
                        subprocess.run(cmd, check=True)
                    except Exception:
                        pass

            # 3. motion_prompt.txt
            action_desc = getattr(shot, "action", "") or ""
            camera_desc = getattr(shot, "camera_motion", "") or ""
            motion_text = f"Action: {action_desc}\nCamera Motion: {camera_desc}\nStyle: Photorealistic cinematic motion, seamless movement, no artifacts."
            with open(shot_dir / "motion_prompt.txt", "w", encoding="utf-8") as f:
                f.write(motion_text)

            # 4. README.txt
            readme_text = f"""GÓI TẠO CLIP HYBRID (KLING / HEDRA) - CẢNH: {shot.shot_id}
- Thời lượng yêu cầu: {dur_sec} giây ({shot.duration_frames} frames @ {fps} fps).
- Tỉ lệ khung hình: 16:9 (1920x1080).
- File hình tham chiếu: image.png
- File giọng đọc khớp khẩu hình: voice.wav

Hướng dẫn sử dụng:
1. Tải image.png và voice.wav lên công cụ Kling AI / Hedra.
2. Dán nội dung motion_prompt.txt vào prompt chuyển động.
3. Xuất clip hoàn thiện và lưu vào:
   input/rendered_clips/{shot.shot_id}.mp4
   (Hoặc nếu là clip có thể lặp lại: input/rendered_clips/{shot.shot_id}.loop.mp4)
"""
            with open(shot_dir / "README.txt", "w", encoding="utf-8") as f:
                f.write(readme_text)

        return target_dir
