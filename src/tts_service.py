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
        """Sinh file mp3 + file mốc thời gian từng từ (.words.json), trả về độ dài chính xác (giây)."""
        import edge_tts
        chosen_voice = voice or self.default_voice
        communicate = edge_tts.Communicate(
            text=text,
            voice=chosen_voice,
            rate=self.voice_rate,
            volume=self.voice_volume,
            boundary="WordBoundary"  # Mặc định của edge-tts là SentenceBoundary
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        events = []
        with open(output_path, "wb") as audio:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    events.append(chunk)

        words = self.boundary_events_to_words(events)
        if not words:
            print(f"[Cảnh báo] Edge-TTS không trả về mốc thời gian từng từ cho {output_path}")
        with open(self.words_path_for(output_path), "w", encoding="utf-8") as f:
            json.dump(words, f, ensure_ascii=False, indent=1)

        return self.get_audio_duration(output_path)

    def generate_audio(self, text: str, output_path: str, voice: str = None) -> float:
        """Wrapper đồng bộ để gọi _generate_single_audio."""
        return asyncio.run(self._generate_single_audio(text, output_path, voice))

    @staticmethod
    def words_path_for(audio_path: str) -> str:
        """shot_01.mp3 -> shot_01.words.json (nằm cạnh file audio)."""
        return Path(audio_path).with_suffix(".words.json").as_posix()

    @staticmethod
    def boundary_events_to_words(events: list) -> list:
        """
        Đổi sự kiện WordBoundary của Edge-TTS (đơn vị 100ns) sang [{text, start, end}] tính bằng giây.
        Với tiếng Việt mỗi sự kiện là 1 âm tiết, dấu câu đã bị Edge-TTS bỏ khỏi text.
        """
        return [
            {
                "text": e["text"],
                "start": round(e["offset"] / 1e7, 4),
                "end": round((e["offset"] + e["duration"]) / 1e7, 4),
            }
            for e in events
        ]

    @staticmethod
    def load_words(audio_path: str) -> list:
        """Đọc file .words.json cạnh file audio; trả về [] nếu chưa có."""
        path = TTSService.words_path_for(audio_path)
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

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
