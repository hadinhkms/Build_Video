import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from run_pipeline import build_srt_entries, format_srt_time, plan_shot_duration
from src.audio.mastering import master_loudness, measure_loudness, parse_loudnorm_json
from src.story_parser import StoryParser
from src.tts_service import TTSService
from src.video_composer import VideoComposer

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
SETTINGS = os.path.join(ROOT, "config", "settings.json")


class TestSrtTiming(unittest.TestCase):
    def test_format_srt_time_rounds_instead_of_truncating(self):
        self.assertEqual(format_srt_time(2.3), "00:00:02,300")  # int() cũ cho ra 02,299
        self.assertEqual(format_srt_time(1.9996), "00:00:02,000")
        self.assertEqual(format_srt_time(3661.5), "01:01:01,500")
        self.assertEqual(format_srt_time(-0.01), "00:00:00,000")

    def test_plan_shot_duration_respects_minimum_and_frame_grid(self):
        self.assertEqual(plan_shot_duration(2.304, 24, 4.0), 4.0)
        d = plan_shot_duration(5.0, 24, 4.0)
        self.assertGreaterEqual(d, 5.6)
        self.assertAlmostEqual(d * 24, round(d * 24), places=2)

    def test_srt_offsets_follow_real_clip_durations(self):
        clips = [
            {"text": "Câu một.", "duration": 4.0, "words": [{"start": 0.1, "end": 2.0}]},
            {"text": "Câu hai.", "duration": 5.5, "words": [{"start": 0.2, "end": 5.4}]},
            {"text": "Không có mốc từ.", "duration": 4.0, "words": []},
        ]
        entries = build_srt_entries(clips)
        self.assertEqual(len(entries), 3)
        self.assertIn("00:00:00,100 --> 00:00:02,300", entries[0])
        # Giữ phụ đề thêm SUBTITLE_HOLD_SEC nhưng không vượt quá cuối clip
        self.assertIn("00:00:04,200 --> 00:00:09,500", entries[1])
        self.assertIn("00:00:09,500 --> 00:00:13,500", entries[2])


class TestSentenceSplit(unittest.TestCase):
    def test_ellipsis_does_not_split_sentence(self):
        text = "Tôi nhận ra kẻ trong phòng khách... không hề có hơi thở.\nCơn mưa trút xuống."
        self.assertEqual(StoryParser.split_sentences(text), [
            "Tôi nhận ra kẻ trong phòng khách... không hề có hơi thở.",
            "Cơn mưa trút xuống.",
        ])

    def test_splits_on_terminal_punctuation(self):
        self.assertEqual(
            StoryParser.split_sentences("Anh đi. Rồi sao? Không! Chờ đã… nhé."),
            ["Anh đi.", "Rồi sao?", "Không!", "Chờ đã… nhé."],
        )

    def test_drops_lines_without_words(self):
        """Dòng chỉ có dấu câu sẽ làm Edge-TTS báo NoAudioReceived nên không được thành shot."""
        text = "Tôi chờ.\n...\nKhông có ai.\n. . .\n***\n……\nHết."
        self.assertEqual(StoryParser.split_sentences(text), ["Tôi chờ.", "Không có ai.", "Hết."])


class _FakeCommunicate:
    last_kwargs = None

    def __init__(self, text, voice, **kwargs):
        _FakeCommunicate.last_kwargs = {"text": text, "voice": voice, **kwargs}

    async def stream(self):
        yield {"type": "audio", "data": b"\xff\xf3"}
        yield {"type": "WordBoundary", "offset": 1_000_000, "duration": 2_000_000, "text": "Đêm"}
        yield {"type": "audio", "data": b"\x00"}
        yield {"type": "WordBoundary", "offset": 3_000_000, "duration": 1_000_000, "text": "tối"}


class TestWordBoundaries(unittest.TestCase):
    def test_events_converted_to_seconds(self):
        events = [
            {"type": "WordBoundary", "offset": 1_000_000, "duration": 2_500_000, "text": "Đêm"},
            {"type": "WordBoundary", "offset": 3_750_000, "duration": 1_250_000, "text": "hôm"},
        ]
        self.assertEqual(TTSService.boundary_events_to_words(events), [
            {"text": "Đêm", "start": 0.1, "end": 0.35},
            {"text": "hôm", "start": 0.375, "end": 0.5},
        ])

    def test_words_path_sits_next_to_audio_with_posix_separators(self):
        self.assertEqual(
            TTSService.words_path_for(os.path.join("assets", "audio", "shots", "shot_01.mp3")),
            "assets/audio/shots/shot_01.words.json",
        )

    def test_generate_audio_requests_word_boundaries_and_writes_words_json(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        audio = os.path.join(tmp, "shot_01.mp3")
        fake_edge_tts = types.SimpleNamespace(Communicate=_FakeCommunicate)

        with mock.patch.dict(sys.modules, {"edge_tts": fake_edge_tts}), \
                mock.patch.object(TTSService, "get_audio_duration", return_value=1.0):
            TTSService(config_path=SETTINGS).generate_audio("Đêm tối.", audio)

        self.assertEqual(_FakeCommunicate.last_kwargs["boundary"], "WordBoundary")
        with open(audio, "rb") as f:
            self.assertEqual(f.read(), b"\xff\xf3\x00")
        self.assertEqual(TTSService.load_words(audio), [
            {"text": "Đêm", "start": 0.1, "end": 0.3},
            {"text": "tối", "start": 0.3, "end": 0.4},
        ])
        with open(TTSService.words_path_for(audio), "r", encoding="utf-8") as f:
            self.assertIn("Đêm", f.read())  # ensure_ascii=False: giữ nguyên tiếng Việt


class TestLoudnormParsing(unittest.TestCase):
    def test_parses_last_json_block(self):
        stderr = (
            "Input #0, mov,mp4 ...\n[Parsed_loudnorm_0 @ 000001]\n"
            '{\n\t"input_i" : "-19.77",\n\t"input_tp" : "-3.88",\n\t"input_lra" : "2.90",\n'
            '\t"input_thresh" : "-29.95",\n\t"target_offset" : "0.27"\n}\n'
        )
        data = parse_loudnorm_json(stderr)
        self.assertEqual(data["input_i"], "-19.77")
        self.assertEqual(data["target_offset"], "0.27")

    def test_returns_none_without_json(self):
        self.assertIsNone(parse_loudnorm_json("no measurement here"))


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def _stream_info(media_path: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration,avg_frame_rate",
         "-of", "json", media_path],
        capture_output=True, text=True, check=True,
    ).stdout
    return {s["codec_type"]: s for s in json.loads(out)["streams"]}


def _ebur128_integrated(media_path: str) -> float:
    err = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", media_path, "-vn", "-af", "ebur128", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1])


@unittest.skipUnless(HAS_FFMPEG, "cần ffmpeg/ffprobe")
class TestFfmpegIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.composer = VideoComposer(settings_path=SETTINGS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_clip_is_padded_to_planned_duration(self):
        """Audio 1.5s nhưng shot 4.0s: cả track hình lẫn track tiếng phải dài 4.0s (trước đây -shortest cắt còn 1.5s)."""
        image, audio = self._make_sources(1.5)
        clip = os.path.join(self.tmp, "clip.mov")

        self.assertTrue(self.composer.render_shot_clip(image, audio, clip, "zoom_in", 4.0))
        streams = _stream_info(clip)
        self.assertAlmostEqual(float(streams["video"]["duration"]), 4.0, delta=0.05)
        self.assertAlmostEqual(float(streams["audio"]["duration"]), 4.0, delta=0.05)

    def test_concat_keeps_audio_in_sync_with_video(self):
        """Ghép nhiều clip rồi master: track audio phải dài bằng track video (trước đây mỗi clip AAC lệch ~21ms)."""
        final, _ = self._concat_and_master([4.0] * 4)
        streams = _stream_info(final)
        self.assertAlmostEqual(float(streams["video"]["duration"]), 16.0, delta=0.05)
        self.assertAlmostEqual(float(streams["audio"]["duration"]), float(streams["video"]["duration"]), delta=0.01)
        self.assertEqual(streams["video"]["avg_frame_rate"], "24/1")  # CFR, không bị làm tròn timestamp

    def test_dynamic_loudnorm_does_not_extend_audio(self):
        """
        Giọng đọc thật luôn rơi vào chế độ dynamic; khi đó loudnorm gắn timestamp khối cuối theo bội 100ms.
        Shot căn theo frame (97/24 = 4.0417s) không phải bội 100ms nên audio từng bị dài hơn video ~33ms.
        """
        final, measured = self._concat_and_master([97 / 24] * 4, target_i=-10.0, target_tp=-9.0)
        self.assertEqual(measured["normalization_type"], "dynamic")
        streams = _stream_info(final)
        self.assertAlmostEqual(float(streams["audio"]["duration"]), float(streams["video"]["duration"]), delta=0.01)

    def test_master_loudness_hits_target(self):
        quiet = os.path.join(self.tmp, "quiet.mp4")
        out = os.path.join(self.tmp, "master.mp4")
        _ffmpeg("-f", "lavfi", "-i", "color=c=black:s=320x180:d=6",
                "-f", "lavfi", "-i", "sine=frequency=300:duration=6",
                "-af", "volume=-24dB", "-c:v", "libx264", "-c:a", "aac", "-shortest", quiet)

        self.assertIsNotNone(measure_loudness(quiet, -14.0, -1.0, 11.0))  # lượt 1 phải đo được
        measured = master_loudness(quiet, out, target_i=-14.0, target_tp=-1.0, target_lra=11.0)
        self.assertEqual(measured["normalization_type"], "linear")  # 2 lượt thật, không rơi về 1 lượt
        self.assertAlmostEqual(_ebur128_integrated(out), -14.0, delta=1.0)  # đo độc lập file đầu ra

    def _concat_and_master(self, durations, target_i=-14.0, target_tp=-1.0):
        image, audio = self._make_sources(1.0)
        clips = []
        for i, duration in enumerate(durations):
            clip = os.path.join(self.tmp, f"clip_{i}.mov")
            self.assertTrue(self.composer.render_shot_clip(image, audio, clip, "zoom_in", round(duration, 4)))
            clips.append(clip)
        prenorm = os.path.join(self.tmp, "master.prenorm.mov")
        final = os.path.join(self.tmp, "master.mp4")
        self.assertTrue(self.composer.concatenate_shots(clips, prenorm))
        measured = master_loudness(prenorm, final, target_i=target_i, target_tp=target_tp)
        self.assertIsNotNone(measured)
        return final, measured

    def _make_sources(self, audio_seconds: float):
        image = os.path.join(self.tmp, "img.jpg")
        audio = os.path.join(self.tmp, "voice.mp3")
        _ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=640x360", "-frames:v", "1", image)
        _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=440:duration={audio_seconds}", "-ar", "24000", audio)
        return image, audio


if __name__ == "__main__":
    unittest.main()
