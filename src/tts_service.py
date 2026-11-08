import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
from src.audio.edge_client import generate_edge_with_retry, synthesize_with_dramatic_pause
from src.audio.tts_utils import combine_rates
from src.vbee_client import VbeeClient

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

TTS_PROVIDERS = ("edge", "vbee")

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

    def _generate_edge_with_retry(
        self, text: str, output_path: str, voice: str, pitch: str, rate: str
    ) -> List[Dict[str, any]]:
        return generate_edge_with_retry(
            text=text, output_path=output_path, voice=voice, pitch=pitch, rate=rate
        )

    def generate_single_audio(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        pitch: str = "+0Hz",
        rate: str = "+0%",
    ) -> List[Dict[str, any]]:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        chosen_voice = voice if self.provider == "vbee" else (voice or self.default_voice)

        if self.provider == "vbee":
            self.vbee.synthesize(text, output_path, chosen_voice)
            words = self.estimate_words(text, *self.detect_speech_span(output_path))
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
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        spk_voice, spk_pitch, spk_rate = self.get_speaker_voice_params(speaker, act)
        chosen_voice = voice if self.provider == "vbee" else (voice or spk_voice)
        chosen_pitch = pitch or spk_pitch
        chosen_rate = rate or spk_rate

        cache_key = hashlib.sha1(
            f"{text}|{chosen_voice}|{chosen_pitch}|{chosen_rate}|{self.provider}".encode("utf-8")
        ).hexdigest()

        words_path = self.words_path_for(output_path)
        meta_path = self.meta_path_for(output_path)

        if os.path.exists(output_path) and os.path.exists(words_path) and os.path.exists(meta_path) and os.path.getsize(output_path) > 0:
            try:
                with open(meta_path, "r", encoding="utf-8") as mf:
                    meta = json.load(mf)
                if meta.get("cache_key") == cache_key:
                    return self.get_audio_duration(output_path)
            except Exception:
                pass

        segments = [s.strip() for s in re.split(r'\.{3}|\u2026', text) if s.strip()]
        if len(segments) > 1:
            words = self._synthesize_with_dramatic_pause(
                segments=segments, output_path=output_path, voice=chosen_voice, pitch=chosen_pitch, rate=chosen_rate
            )
        else:
            words = self.generate_single_audio(
                text=text, output_path=output_path, voice=chosen_voice, pitch=chosen_pitch, rate=chosen_rate
            )

        with open(words_path, "w", encoding="utf-8") as f:
            json.dump(words, f, ensure_ascii=False, indent=2)

        meta_data = {
            "cache_key": cache_key, "speaker": speaker, "voice": chosen_voice,
            "pitch": chosen_pitch, "rate": chosen_rate, "provider": self.provider, "text": text,
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=2)

        return self.get_audio_duration(output_path)

    def _synthesize_with_dramatic_pause(
        self, segments: List[str], output_path: str, voice: str, pitch: str, rate: str
    ) -> List[Dict[str, any]]:
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
