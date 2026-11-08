import math
import shutil
import tempfile
import unittest
import wave
from pathlib import Path
import numpy as np

from src.audio.envelope import AudioEnvelopeCalculator, compute_shot_envelope


class TestAudioEnvelope(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.fps = 24
        self.sr = 16000

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _write_wav(self, filename: str, samples: np.ndarray):
        path = self.test_dir / filename
        int16_samples = np.clip(samples * 32767.0, -32768, 32767).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sr)
            wf.writeframes(int16_samples.tobytes())
        return path

    def test_silent_audio_produces_all_zeros(self):
        # 2 giây im lặng
        silent_samples = np.zeros(self.sr * 2, dtype=np.float32)
        wav_path = self._write_wav("silent.wav", silent_samples)

        calc = AudioEnvelopeCalculator(fps=self.fps, target_sr=self.sr)
        env = calc.compute_full_envelope(wav_path)

        self.assertEqual(len(env), 48)
        self.assertTrue(all(v == 0.0 for v in env))

    def test_silence_greater_than_200ms_is_zero(self):
        # 1 giây có tiếng (440Hz sine wave), sau đó là 0.5s (500ms > 200ms) im lặng
        t_sound = np.linspace(0, 1.0, self.sr, endpoint=False)
        sound = 0.8 * np.sin(2 * np.pi * 440 * t_sound)
        silence = np.zeros(int(self.sr * 0.5), dtype=np.float32)
        combined = np.concatenate([sound, silence])

        wav_path = self._write_wav("sound_silence.wav", combined)

        calc = AudioEnvelopeCalculator(fps=self.fps, target_sr=self.sr)
        env = calc.compute_full_envelope(wav_path)

        # 1s sound = 24 frames; 0.5s silence = 12 frames
        self.assertGreaterEqual(len(env), 36)
        # Khung hình trong đoạn có tiếng phải có biên độ
        self.assertGreater(max(env[:24]), 0.3)
        # Khung hình ở cuối đoạn im lặng (sau khi release 80ms tắt hẳn) phải về 0.0
        self.assertEqual(env[-1], 0.0)
        self.assertEqual(env[-2], 0.0)

    def test_slice_envelope_pads_to_duration_in_frames(self):
        calc = AudioEnvelopeCalculator(fps=self.fps, target_sr=self.sr)
        full_env = [0.5, 0.6, 0.7, 0.8]  # chỉ 4 frames

        # Yêu cầu 10 frames
        sliced = calc.slice_envelope(full_env, start_in_file_sec=0.0, duration_in_frames=10)
        self.assertEqual(len(sliced), 10)
        self.assertEqual(sliced[:4], [0.5, 0.6, 0.7, 0.8])
        self.assertEqual(sliced[4:], [0.0] * 6)

    def test_sub_shot_slicing_consistency(self):
        # 4 giây audio (96 frames)
        t = np.linspace(0, 4.0, self.sr * 4, endpoint=False)
        samples = 0.7 * np.sin(2 * np.pi * 300 * t)
        wav_path = self._write_wav("full_sentence.wav", samples)

        calc = AudioEnvelopeCalculator(fps=self.fps, target_sr=self.sr)
        full_env = calc.compute_full_envelope(wav_path)
        self.assertEqual(len(full_env), 96)

        # Cảnh con 1: 0.0s đến 2.0s (48 frames)
        sub1 = calc.slice_envelope(full_env, start_in_file_sec=0.0, duration_in_frames=48)
        # Cảnh con 2: 2.0s đến 4.0s (48 frames)
        sub2 = calc.slice_envelope(full_env, start_in_file_sec=2.0, duration_in_frames=48)

        self.assertEqual(len(sub1), 48)
        self.assertEqual(len(sub2), 48)
        self.assertEqual(sub1 + sub2, full_env)

    def test_dialogue_speaker_rules(self):
        samples = np.ones(self.sr * 2, dtype=np.float32) * 0.5
        wav_path = self._write_wav("speech.wav", samples)

        # 1. Narrator (không phải đối thoại) -> None
        env_narrator = compute_shot_envelope(
            audio_path=wav_path,
            start_in_file_sec=0.0,
            duration_in_frames=48,
            is_dialogue=False,
            speaker="narrator",
            on_screen_character_id="nhan_vat_chinh",
        )
        self.assertIsNone(env_narrator)

        # 2. Dialogue nhưng speaker không khớp on_screen_character_id -> None
        env_other = compute_shot_envelope(
            audio_path=wav_path,
            start_in_file_sec=0.0,
            duration_in_frames=48,
            is_dialogue=True,
            speaker="nguoi_la",
            on_screen_character_id="nhan_vat_chinh",
        )
        self.assertIsNone(env_other)

        # 3. Dialogue và speaker khớp nhân vật trên hình -> mảng float dài đúng 48
        env_valid = compute_shot_envelope(
            audio_path=wav_path,
            start_in_file_sec=0.0,
            duration_in_frames=48,
            is_dialogue=True,
            speaker="nhan_vat_chinh",
            on_screen_character_id="nhan_vat_chinh",
        )
        self.assertIsNotNone(env_valid)
        self.assertEqual(len(env_valid), 48)


if __name__ == "__main__":
    unittest.main()
