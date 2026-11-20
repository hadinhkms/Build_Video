import json
import shutil
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

import numpy as np

from src.audio.envelope import (
    AudioEnvelopeCalculator,
    batch_compute_envelopes,
    compute_shot_envelope,
    envelope_cache_path_for,
)
from src.audio.foley_planner import FoleyPlanner
from src.core.models import Effects, NarrativeAct, Shot, ShotKind, Storyboard, Visual
from src.export.scene_builder import build_scenes


class TestEnvelopeCacheAndDedup(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.fps = 24
        self.sr = 16000

    def _make_wav(self, name: str, duration_sec: float = 4.0, freq: float = 350.0) -> Path:
        p = self.tmp / name
        t = np.linspace(0, duration_sec, int(self.sr * duration_sec), endpoint=False)
        # Tạo biến thiên biên độ rõ rệt giữa đầu và cuối file
        mod = 0.5 + 0.5 * np.sin(2 * np.pi * 1.2 * t)
        samples = (0.75 * mod * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        int16 = np.clip(samples * 32767.0, -32768, 32767).astype(np.int16)
        with wave.open(str(p), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sr)
            wf.writeframes(int16.tobytes())
        return p

    def test_disk_cache_is_bit_exact_and_invalidates_on_change(self):
        wav = self._make_wav("dialogue_01.wav", duration_sec=3.0)
        calc = AudioEnvelopeCalculator(fps=self.fps, target_sr=self.sr)

        # Tham chiếu không dùng cache
        raw_env = calc.compute_full_envelope(wav, use_cache=False)
        cache_file = envelope_cache_path_for(wav)
        self.assertFalse(cache_file.exists())

        # Lần 1 dùng cache -> ghi tệp .envelope.json
        env1 = calc.compute_full_envelope(wav, use_cache=True)
        self.assertTrue(cache_file.exists())
        self.assertEqual(env1, raw_env)

        meta = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertIn("source_sha1", meta)
        self.assertEqual(meta["fps"], self.fps)
        self.assertEqual(meta["target_sr"], self.sr)
        self.assertEqual(meta["envelope"], raw_env)

        # Lần 2 -> trúng cache 100%, KHÔNG gọi _decode_to_pcm
        with mock.patch.object(calc, "_decode_to_pcm", side_effect=AssertionError("Phải trúng cache!")):
            env2 = calc.compute_full_envelope(wav, use_cache=True)
        self.assertEqual(env2, raw_env)

        # Đổi fps -> cache miss và tính lại
        calc_30 = AudioEnvelopeCalculator(fps=30, target_sr=self.sr)
        env_30 = calc_30.compute_full_envelope(wav, use_cache=True)
        self.assertNotEqual(len(env_30), len(raw_env))

        # Ghi lại cache 24fps rồi đổi nội dung file audio -> SHA1 đổi -> cache miss
        calc.compute_full_envelope(wav, use_cache=True)
        self._make_wav("dialogue_01.wav", duration_sec=1.5, freq=500.0)
        env_new = calc.compute_full_envelope(wav, use_cache=True)
        self.assertEqual(len(env_new), 36)  # 1.5s * 24fps

    def test_batch_compute_envelopes_deduplicates_and_matches_single(self):
        w1 = self._make_wav("a.wav", duration_sec=2.0, freq=220.0)
        w2 = self._make_wav("b.wav", duration_sec=2.5, freq=440.0)
        w3 = self._make_wav("c.wav", duration_sec=3.0, freq=660.0)

        decode_calls = []
        orig_decode = AudioEnvelopeCalculator._decode_to_pcm

        def spy_decode(self_c, path):
            decode_calls.append(Path(path).resolve())
            return orig_decode(self_c, path)

        with mock.patch.object(AudioEnvelopeCalculator, "_decode_to_pcm", autospec=True, side_effect=spy_decode):
            # Truyền trùng w1 ba lần -> chỉ giải mã đúng 1 lần cho mỗi file duy nhất
            batch_res = batch_compute_envelopes([w1, w1, w2, w1, w3], fps=self.fps, max_workers=3)

        self.assertEqual(len(decode_calls), 3)
        self.assertEqual(set(decode_calls), {w1.resolve(), w2.resolve(), w3.resolve()})

        # Lần 2 -> toàn bộ trúng cache đĩa (0 lần decode)
        with mock.patch.object(AudioEnvelopeCalculator, "_decode_to_pcm", side_effect=AssertionError("Phải hit cache!")):
            batch_hit = batch_compute_envelopes([w1, w2, w3], fps=self.fps, max_workers=3)
        self.assertEqual(batch_hit, batch_res)

    def test_scene_builder_deduplicates_split_dialogue_shots_and_matches_compute_shot_envelope(self):
        shared_audio = self._make_wav("shot_05.wav", duration_sec=6.0)
        narrator_audio = self._make_wav("shot_06.wav", duration_sec=3.0)

        shots = [
            Shot(
                shot_id="shot_05a",
                parent_id="shot_05",
                kind=ShotKind.STORY,
                narrative_act=NarrativeAct.RISING,
                raw_text="Anh đã biết chuyện này từ lâu,",
                voice_text="Anh đã biết chuyện này từ lâu,",
                is_dialogue=True,
                speaker="nam",
                on_screen_character_id="nam",
                duration_frames=48,
                duration=2.0,
                audio_file=str(shared_audio),
                audio_start_in_file_sec=0.0,
                shot_type="medium",
                camera_motion="zoom_in",
            ),
            Shot(
                shot_id="shot_05b",
                parent_id="shot_05",
                kind=ShotKind.STORY,
                narrative_act=NarrativeAct.RISING,
                raw_text="nhưng không dám nói ra sự thật,",
                voice_text="nhưng không dám nói ra sự thật,",
                is_dialogue=True,
                speaker="nam",
                on_screen_character_id="nam",
                duration_frames=48,
                duration=2.0,
                audio_file=str(shared_audio),
                audio_start_in_file_sec=2.0,
                shot_type="closeup",
                camera_motion="zoom_out",
            ),
            Shot(
                shot_id="shot_05c",
                parent_id="shot_05",
                kind=ShotKind.STORY,
                narrative_act=NarrativeAct.RISING,
                raw_text="vì sợ làm tổn thương mọi người.",
                voice_text="vì sợ làm tổn thương mọi người.",
                is_dialogue=True,
                speaker="nam",
                on_screen_character_id="nam",
                duration_frames=48,
                duration=2.0,
                audio_file=str(shared_audio),
                audio_start_in_file_sec=4.0,
                shot_type="over_shoulder",
                camera_motion="pan_left",
            ),
            Shot(
                shot_id="shot_06",
                kind=ShotKind.STORY,
                narrative_act=NarrativeAct.SETUP,
                raw_text="Lời dẫn chuyện không mở miệng.",
                voice_text="Lời dẫn chuyện không mở miệng.",
                is_dialogue=False,
                speaker="narrator",
                on_screen_character_id="nam",
                duration_frames=72,
                duration=3.0,
                audio_file=str(narrator_audio),
                audio_start_in_file_sec=0.0,
                shot_type="wide",
                camera_motion="static",
            ),
        ]
        sb = Storyboard(chapter_id="env_ch", title="Env Test", shots=shots)
        dummy_vis = Visual(
            mode="full_image", image_src="chapters/env_ch/images/x.jpg",
            background_src=None, character_src=None, clip_src=None,
            character_anchor=None, crop_rect=None, clip_duration_sec=None,
            clip_fit=None, face_rig=None,
        )
        dummy_eff = Effects(rain="off", rain_region=None, flicker=False)
        visuals = {s.shot_id: dummy_vis for s in shots}
        effects = {s.shot_id: dummy_eff for s in shots}
        grades = {s.shot_id: None for s in shots}

        foley = mock.MagicMock(spec=FoleyPlanner)
        foley.plan_sfx_for_scene.return_value = []

        pub_dir = self.tmp / "pub"
        (pub_dir / "audio").mkdir(parents=True, exist_ok=True)

        decode_calls = []
        orig_decode = AudioEnvelopeCalculator._decode_to_pcm

        def spy_decode(self_c, path):
            decode_calls.append(Path(path).resolve())
            return orig_decode(self_c, path)

        with mock.patch.object(AudioEnvelopeCalculator, "_decode_to_pcm", autospec=True, side_effect=spy_decode):
            scenes, _ = build_scenes(
                storyboard=sb,
                story_visuals=visuals,
                story_effects=effects,
                story_grades=grades,
                foley_planner=foley,
                words_map={},
                emotion_keywords=[],
                root=self.tmp,
                pub_chapter_dir=pub_dir,
                chapter_id="env_ch",
                fps=self.fps,
            )

        # 3 cảnh con chung 1 file dialogue -> chỉ decode ĐÚNG 1 LẦN! (narrator không decode!)
        self.assertEqual(decode_calls, [shared_audio.resolve()])
        self.assertIsNone(scenes[3].mouth_envelope)

        # Kiểm chứng độ chính xác bit-exact với compute_shot_envelope()
        for idx, offset in enumerate((0.0, 2.0, 4.0)):
            ref = compute_shot_envelope(
                audio_path=shared_audio,
                start_in_file_sec=offset,
                duration_in_frames=48,
                is_dialogue=True,
                speaker="nam",
                on_screen_character_id="nam",
                fps=self.fps,
            )
            self.assertEqual(scenes[idx].mouth_envelope, ref)

    def test_corrupted_envelope_cache_self_heals_and_parallel_writes_leave_no_tmp(self):
        from concurrent.futures import ThreadPoolExecutor

        wav = self._make_wav("corrupt_test.wav", duration_sec=2.0, freq=300.0)
        calc = AudioEnvelopeCalculator(fps=self.fps, target_sr=self.sr)
        expected = calc.compute_full_envelope(wav, use_cache=False)

        cache_file = envelope_cache_path_for(wav)
        # Ghi JSON hỏng hoàn toàn
        cache_file.write_text("{corrupted_json: [1, 2,", encoding="utf-8")
        recovered = calc.compute_full_envelope(wav, use_cache=True)
        self.assertEqual(recovered, expected)

        # Kiểm tra tệp cache đã tự hồi phục thành JSON hợp lệ
        repaired = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertEqual(repaired["envelope"], expected)

        # Ghi cấu trúc envelope chứa phần tử sai kiểu -> cũng phải tự hồi phục
        cache_file.write_text(
            json.dumps({
                "source_sha1": repaired["source_sha1"],
                "fps": self.fps,
                "target_sr": self.sr,
                "envelope": ["bad_float"],
            }),
            encoding="utf-8",
        )
        recovered2 = calc.compute_full_envelope(wav, use_cache=True)
        self.assertEqual(recovered2, expected)

        # Nhiều luồng đồng thời ghi cache cho cùng 1 file audio không bị đụng tên file tạm
        cache_file.unlink()
        with ThreadPoolExecutor(max_workers=6) as pool:
            futs = [
                pool.submit(AudioEnvelopeCalculator(fps=self.fps, target_sr=self.sr).compute_full_envelope, wav, True)
                for _ in range(6)
            ]
            outputs = [f.result() for f in futs]
        for out in outputs:
            self.assertEqual(out, expected)
        leftover_tmp = [p for p in self.tmp.iterdir() if ".tmp." in p.name]
        self.assertEqual(leftover_tmp, [])


if __name__ == "__main__":
    unittest.main()
