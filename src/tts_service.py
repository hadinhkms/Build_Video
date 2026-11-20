import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import re
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.audio.audio_utils import (
    boundary_events_to_words,
    detect_speech_span,
    estimate_words,
    get_audio_duration,
    get_audio_stream_props,
    load_words,
    meta_path_for,
    words_path_for,
)
from src.audio.edge_client import (
    _gather_fail_fast,
    _safe_unlink,
    generate_edge_batch_async,
    generate_edge_with_retry,
    generate_edge_with_retry_async,
    synthesize_with_dramatic_pause,
    synthesize_with_dramatic_pause_async,
)
from src.audio.tts_utils import combine_rates
from src.vbee_client import VbeeClient, VbeeError

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

TTS_PROVIDERS = ("edge", "vbee")


def _atomic_write_json(path: str, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}"
    tmp = p.with_name(f".{p.name}.tmp.{token}")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(str(tmp), str(p))
    except BaseException:
        _safe_unlink(str(tmp))
        raise

class TTSService:
    def __init__(
        self,
        config_path: str = "config/settings.json",
        characters_path: str = "config/characters.json",
        provider: Optional[str] = None,
    ):
        with open(config_path, "r", encoding="utf-8") as f:
            self.settings = json.load(f)

        self.characters = {}
        if os.path.exists(characters_path):
            with open(characters_path, "r", encoding="utf-8") as f:
                self.characters = json.load(f).get("characters", {})

        self.audio_cfg = self.settings.get("audio", {})
        self.default_voice = self.audio_cfg.get("default_voice", "vi-VN-NamMinhNeural")
        self.narrator_cfg = self.audio_cfg.get("narrator", {"voice": self.default_voice, "pitch": "+0Hz", "rate": "+0%"})
        self.rate_by_act = self.audio_cfg.get("rate_by_act", {"RISING": "+5%", "CLIMAX": "+8%"})
        self.dramatic_pause_sec = float(self.audio_cfg.get("dramatic_pause_sec", 0.9))
        self.tts_concurrency = max(1, int(self.audio_cfg.get("tts_concurrency", 5)))

        self.provider = (provider or self.audio_cfg.get("provider", "edge")).lower()
        if self.provider not in TTS_PROVIDERS:
            raise ValueError(f"TTS provider phải là một trong {TTS_PROVIDERS}, nhận được '{self.provider}'")

        self.vbee = VbeeClient.from_settings(self.audio_cfg.get("vbee", {})) if self.provider == "vbee" else None

    def get_speaker_voice_params(self, speaker: str, act: Optional[str] = None) -> Tuple[str, str, str]:
        act_extra_rate = self.rate_by_act.get(act, "+0%") if act else "+0%"
        if speaker in self.characters:
            char_cfg = self.characters[speaker]
            voice = char_cfg.get("voice", self.default_voice)
            pitch = char_cfg.get("pitch", "+0Hz")
            base_rate = char_cfg.get("rate", "+0%")
        else:
            voice = self.narrator_cfg.get("voice", self.default_voice)
            pitch = self.narrator_cfg.get("pitch", "+0Hz")
            base_rate = self.narrator_cfg.get("rate", "+0%")
        return voice, pitch, combine_rates(base_rate, act_extra_rate)

    def resolve_effective_concurrency(self, requested: Optional[int] = None) -> int:
        """Tính mức song song an toàn theo provider (Edge mặc định 5, Vbee tối đa 2)."""
        base = int(requested) if requested is not None else self.tts_concurrency
        base = max(1, base)
        if self.provider == "vbee":
            return min(2, base)
        return base

    def compute_cache_key(self, text: str, voice: Optional[str], pitch: str, rate: str) -> str:
        return hashlib.sha1(
            f"{text}|{voice}|{pitch}|{rate}|{self.provider}".encode("utf-8")
        ).hexdigest()

    def _is_cache_hit(self, output_path: str, cache_key: str) -> bool:
        words_path = self.words_path_for(output_path)
        meta_path = self.meta_path_for(output_path)
        if (
            os.path.exists(output_path)
            and os.path.exists(words_path)
            and os.path.exists(meta_path)
            and os.path.getsize(output_path) > 0
        ):
            try:
                with open(meta_path, "r", encoding="utf-8") as mf:
                    meta = json.load(mf)
                return meta.get("cache_key") == cache_key
            except Exception:
                return False
        return False

    def _generate_edge_with_retry(
        self, text: str, output_path: str, voice: str, pitch: str, rate: str
    ) -> List[Dict[str, Any]]:
        return generate_edge_with_retry(
            text=text, output_path=output_path, voice=voice, pitch=pitch, rate=rate
        )

    async def _generate_edge_with_retry_async(
        self, text: str, output_path: str, voice: str, pitch: str, rate: str
    ) -> List[Dict[str, Any]]:
        return await generate_edge_with_retry_async(
            text=text, output_path=output_path, voice=voice, pitch=pitch, rate=rate
        )

    def generate_single_audio(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        pitch: str = "+0Hz",
        rate: str = "+0%",
    ) -> List[Dict[str, Any]]:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        chosen_voice = voice if self.provider == "vbee" else (voice or self.default_voice)

        if self.provider == "vbee":
            try:
                self.vbee.synthesize(text, output_path, chosen_voice)
                words = self.estimate_words(text, *self.detect_speech_span(output_path))
            except BaseException:
                _safe_unlink(output_path)
                raise
        else:
            words = self._generate_edge_with_retry(
                text=text, output_path=output_path, voice=chosen_voice, pitch=pitch, rate=rate
            )
        return words

    def generate_audio(
        self,
        text: str,
        output_path: str,
        speaker: str = "narrator",
        act: Optional[str] = None,
        voice: Optional[str] = None,
        pitch: Optional[str] = None,
        rate: Optional[str] = None,
    ) -> float:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        spk_voice, spk_pitch, spk_rate = self.get_speaker_voice_params(speaker, act)
        chosen_voice = voice if self.provider == "vbee" else (voice or spk_voice)
        chosen_pitch = pitch or spk_pitch
        chosen_rate = rate or spk_rate

        cache_key = self.compute_cache_key(text, chosen_voice, chosen_pitch, chosen_rate)
        words_path = self.words_path_for(output_path)
        meta_path = self.meta_path_for(output_path)

        if self._is_cache_hit(output_path, cache_key):
            return self.get_audio_duration(output_path)

        segments = [s.strip() for s in re.split(r'\.{3}|\u2026', text) if s.strip()]
        try:
            if len(segments) > 1:
                words = self._synthesize_with_dramatic_pause(
                    segments=segments, output_path=output_path, voice=chosen_voice, pitch=chosen_pitch, rate=chosen_rate
                )
            else:
                words = self.generate_single_audio(
                    text=text, output_path=output_path, voice=chosen_voice, pitch=chosen_pitch, rate=chosen_rate
                )
        except BaseException:
            _safe_unlink(output_path)
            raise

        _atomic_write_json(words_path, words)

        meta_data = {
            "cache_key": cache_key, "speaker": speaker, "voice": chosen_voice,
            "pitch": chosen_pitch, "rate": chosen_rate, "provider": self.provider, "text": text,
        }
        _atomic_write_json(meta_path, meta_data)

        return self.get_audio_duration(output_path)

    async def generate_audio_async(
        self,
        text: str,
        output_path: str,
        speaker: str = "narrator",
        act: Optional[str] = None,
        voice: Optional[str] = None,
        pitch: Optional[str] = None,
        rate: Optional[str] = None,
        sem: Optional[asyncio.Semaphore] = None,
    ) -> float:
        """Tạo 1 tệp âm thanh bất đồng bộ; câu trúng cache SHA1 hoàn tất ngay không chiếm slot semaphore."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        spk_voice, spk_pitch, spk_rate = self.get_speaker_voice_params(speaker, act)
        chosen_voice = voice if self.provider == "vbee" else (voice or spk_voice)
        chosen_pitch = pitch or spk_pitch
        chosen_rate = rate or spk_rate

        cache_key = self.compute_cache_key(text, chosen_voice, chosen_pitch, chosen_rate)
        words_path = self.words_path_for(output_path)
        meta_path = self.meta_path_for(output_path)

        # Trúng cache SHA1 -> KHÔNG chiếm slot semaphore!
        if self._is_cache_hit(output_path, cache_key):
            return await asyncio.to_thread(self.get_audio_duration, output_path)

        segments = [s.strip() for s in re.split(r'\.{3}|\u2026', text) if s.strip()]

        try:
            if self.provider == "edge":
                if len(segments) > 1:
                    words = await synthesize_with_dramatic_pause_async(
                        segments=segments,
                        output_path=output_path,
                        voice=chosen_voice,
                        pitch=chosen_pitch,
                        rate=chosen_rate,
                        dramatic_pause_sec=self.dramatic_pause_sec,
                        sem=sem,
                        single_async_fn=self._generate_edge_with_retry_async,
                    )
                else:
                    if sem is not None:
                        async with sem:
                            words = await self._generate_edge_with_retry_async(
                                text=text,
                                output_path=output_path,
                                voice=chosen_voice,
                                pitch=chosen_pitch,
                                rate=chosen_rate,
                            )
                    else:
                        words = await self._generate_edge_with_retry_async(
                            text=text,
                            output_path=output_path,
                            voice=chosen_voice,
                            pitch=chosen_pitch,
                            rate=chosen_rate,
                        )
            else:
                # Provider Vbee (blocking HTTP) -> chạy an toàn qua asyncio.to_thread với giới hạn semaphore <= 2
                async def _run_vbee() -> List[Dict[str, Any]]:
                    if len(segments) > 1:
                        return await asyncio.to_thread(
                            self._synthesize_with_dramatic_pause,
                            segments,
                            output_path,
                            chosen_voice,
                            chosen_pitch,
                            chosen_rate,
                        )
                    return await asyncio.to_thread(
                        self.generate_single_audio,
                        text,
                        output_path,
                        chosen_voice,
                        chosen_pitch,
                        chosen_rate,
                    )

                if sem is not None:
                    async with sem:
                        words = await _run_vbee()
                else:
                    words = await _run_vbee()
        except BaseException:
            _safe_unlink(output_path)
            raise

        _atomic_write_json(words_path, words)

        meta_data = {
            "cache_key": cache_key, "speaker": speaker, "voice": chosen_voice,
            "pitch": chosen_pitch, "rate": chosen_rate, "provider": self.provider, "text": text,
        }
        _atomic_write_json(meta_path, meta_data)

        return await asyncio.to_thread(self.get_audio_duration, output_path)

    async def generate_audio_batch_async(
        self,
        tasks: Sequence[Dict[str, Any]],
        max_concurrency: Optional[int] = None,
    ) -> List[float]:
        """Tổng hợp song song danh sách câu thoại, bảo toàn đúng thứ tự đầu vào."""
        if not tasks:
            return []
        effective_conc = self.resolve_effective_concurrency(max_concurrency)
        sem = asyncio.Semaphore(effective_conc)
        coros = [
            self.generate_audio_async(
                text=str(task["text"]),
                output_path=str(task["output_path"]),
                speaker=str(task.get("speaker", "narrator")),
                act=task.get("act"),
                voice=task.get("voice"),
                pitch=task.get("pitch"),
                rate=task.get("rate"),
                sem=sem,
            )
            for task in tasks
        ]
        return await _gather_fail_fast(coros)

    def generate_audio_batch(
        self,
        tasks: Sequence[Dict[str, Any]],
        max_concurrency: Optional[int] = None,
    ) -> List[float]:
        """Wrapper đồng bộ chạy `generate_audio_batch_async()` cho pipeline (an toàn cả khi đã có event loop)."""
        if not tasks:
            return []

        def _run_in_new_loop() -> List[float]:
            return asyncio.run(
                self.generate_audio_batch_async(tasks, max_concurrency=max_concurrency)
            )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return _run_in_new_loop()

        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_run_in_new_loop).result()

    def _synthesize_with_dramatic_pause(
        self, segments: List[str], output_path: str, voice: str, pitch: str, rate: str
    ) -> List[Dict[str, Any]]:
        return synthesize_with_dramatic_pause(
            segments=segments, output_path=output_path, voice=voice, pitch=pitch, rate=rate,
            dramatic_pause_sec=self.dramatic_pause_sec, single_audio_fn=self.generate_single_audio,
        )

    words_path_for = staticmethod(words_path_for)
    meta_path_for = staticmethod(meta_path_for)
    load_words = staticmethod(load_words)
    boundary_events_to_words = staticmethod(boundary_events_to_words)
    estimate_words = staticmethod(estimate_words)
    detect_speech_span = staticmethod(detect_speech_span)
    get_audio_duration = staticmethod(get_audio_duration)
    get_audio_stream_props = staticmethod(get_audio_stream_props)
