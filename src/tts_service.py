import asyncio
import json
import os
import subprocess
from pathlib import Path

class TTSService:
    def __init__(self, config_path="config/settings.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.settings = json.load(f)
        self.audio_cfg = self.settings.get("audio", {})
        self.default_voice = self.audio_cfg.get("default_voice", "vi-VN-NamMinhNeural")
        self.voice_rate = self.audio_cfg.get("voice_rate", "+0%")
        self.voice_volume = self.audio_cfg.get("voice_volume", "+0%")

    async def _generate_single_audio(self, text: str, output_path: str, voice: str = None) -> float:
        """Sinh file mp3 từ văn bản và trả về độ dài chính xác (giây)."""
        import edge_tts
        chosen_voice = voice or self.default_voice
        communicate = edge_tts.Communicate(
            text=text,
            voice=chosen_voice,
            rate=self.voice_rate,
            volume=self.voice_volume
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        await communicate.save(output_path)
        return self.get_audio_duration(output_path)

    def generate_audio(self, text: str, output_path: str, voice: str = None) -> float:
        """Wrapper đồng bộ để gọi _generate_single_audio."""
        return asyncio.run(self._generate_single_audio(text, output_path, voice))

    @staticmethod
    def get_audio_duration(file_path: str) -> float:
        """Dùng ffprobe để lấy chính xác thời lượng file audio."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            print(f"[Cảnh báo] Không thể đo thời lượng audio bằng ffprobe: {e}")
            return 5.0
