import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.tts_service import TTSService
from src.vbee_client import DUMMY_CALLBACK_URL, VbeeClient, VbeeError

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
SETTINGS = os.path.join(ROOT, "config", "settings.json")
FAKE_CREDS = {"VBEE_APP_ID": "app-123", "VBEE_ACCESS_TOKEN": "tok-456"}


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        if self._payload is None:
            raise ValueError("không phải JSON")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class _FakeSession:
    """Trả lần lượt các phản hồi đã xếp sẵn; phần tử là Exception thì raise."""

    def __init__(self, posts=(), gets=()):
        self.posts, self.gets, self.calls = list(posts), list(gets), []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"method": "POST", "url": url, "json": json, "headers": headers})
        return self._next(self.posts)

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"method": "GET", "url": url, "headers": headers})
        return self._next(self.gets)

    @staticmethod
    def _next(queue):
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ok(result):
    return _FakeResponse(payload={"status": 1, "result": result})


class TestProviderSelection(unittest.TestCase):
    def test_defaults_to_provider_in_settings(self):
        self.assertEqual(TTSService(config_path=SETTINGS).provider, "edge")

    def test_argument_overrides_settings_and_reads_vbee_config(self):
        with mock.patch.dict(os.environ, FAKE_CREDS), mock.patch("dotenv.load_dotenv"):
            tts = TTSService(config_path=SETTINGS, provider="vbee")
        self.assertEqual(tts.provider, "vbee")
        self.assertEqual(tts.vbee.app_id, "app-123")
        self.assertEqual(tts.vbee.voice_code, "n_hanoi_male_protrainer_education_vc")

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(ValueError):
            TTSService(config_path=SETTINGS, provider="google")

    def test_vbee_without_credentials_explains_what_to_do(self):
        with mock.patch.dict(os.environ), mock.patch("dotenv.load_dotenv"):
            for key in FAKE_CREDS:
                os.environ.pop(key, None)
            with self.assertRaisesRegex(VbeeError, "VBEE_APP_ID"):
                TTSService(config_path=SETTINGS, provider="vbee")


class TestVbeeClient(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.out = os.path.join(self.tmp, "shot_01.mp3")

    def _client(self, session, **kwargs):
        return VbeeClient("app-123", "tok-456", poll_interval_sec=0, session=session, **kwargs)

    def test_submits_polls_then_downloads(self):
        session = _FakeSession(
            posts=[_ok({"request_id": "r1", "status": "IN_PROGRESS"})],
            gets=[
                _ok({"request_id": "r1", "status": "IN_PROGRESS"}),
                _ok({"request_id": "r1", "status": "SUCCESS", "audio_link": "https://cdn.vbee.vn/r1.mp3"}),
                _FakeResponse(content=b"ID3mp3"),
            ],
        )
        self._client(session).synthesize("Đêm hôm đó.", self.out)

        with open(self.out, "rb") as f:
            self.assertEqual(f.read(), b"ID3mp3")
        submit = session.calls[0]
        self.assertEqual(submit["url"], "https://vbee.vn/api/v1/tts")
        self.assertEqual(submit["headers"]["Authorization"], "Bearer tok-456")
        self.assertEqual(submit["json"]["app_id"], "app-123")
        self.assertEqual(submit["json"]["input_text"], "Đêm hôm đó.")
        self.assertEqual(submit["json"]["voice_code"], "n_hanoi_male_protrainer_education_vc")
        self.assertEqual(submit["json"]["callback_url"], DUMMY_CALLBACK_URL)  # API bắt buộc
        self.assertEqual(session.calls[1]["url"], "https://vbee.vn/api/v1/tts/r1")
        self.assertIsNone(session.calls[-1]["headers"])  # không gửi token sang CDN

    def test_voice_code_argument_overrides_default(self):
        session = _FakeSession(
            posts=[_ok({"request_id": "r1", "audio_link": "https://cdn/r1.mp3"})],
            gets=[_FakeResponse(content=b"x")],
        )
        self._client(session).synthesize("Chào.", self.out, voice_code="n_hanoi_female_nguyetnga2_book_vc")
        self.assertEqual(session.calls[0]["json"]["voice_code"], "n_hanoi_female_nguyetnga2_book_vc")

    def test_api_error_is_reported_without_retry(self):
        session = _FakeSession(posts=[_FakeResponse(401, {
            "status": 0, "error_code": "INVALID_TOKEN", "error_message": "Token không hợp lệ"})])
        with self.assertRaisesRegex(VbeeError, "Token không hợp lệ"):
            self._client(session).synthesize("Chào.", self.out)
        self.assertEqual(len(session.calls), 1)

    def test_network_and_server_errors_are_retried(self):
        session = _FakeSession(
            posts=[_FakeResponse(503), requests.ConnectionError("mất mạng"),
                   _ok({"request_id": "r1", "audio_link": "https://cdn/r1.mp3"})],
            gets=[_FakeResponse(content=b"x")],
        )
        with mock.patch("src.vbee_client.time.sleep"):
            self._client(session).synthesize("Chào.", self.out)
        self.assertEqual([c["method"] for c in session.calls], ["POST", "POST", "POST", "GET"])

    def test_failure_status_raises(self):
        session = _FakeSession(posts=[_ok({"request_id": "r1", "status": "IN_PROGRESS"})],
                               gets=[_ok({"request_id": "r1", "status": "FAILURE"})])
        with self.assertRaisesRegex(VbeeError, "thất bại"):
            self._client(session).synthesize("Chào.", self.out)

    def test_poll_timeout_raises(self):
        session = _FakeSession(posts=[_ok({"request_id": "r1", "status": "IN_PROGRESS"})])
        with self.assertRaisesRegex(VbeeError, "r1"):
            self._client(session, poll_timeout_sec=0).synthesize("Chào.", self.out)


class TestEstimatedWordTimings(unittest.TestCase):
    def test_spreads_syllables_over_speech_span_by_length(self):
        self.assertEqual(TTSService.estimate_words("Đêm, tối quá.", 0.2, 2.0), [
            {"text": "Đêm", "start": 0.2, "end": 0.8},
            {"text": "tối", "start": 0.8, "end": 1.4},
            {"text": "quá", "start": 1.4, "end": 2.0},
        ])

    def test_text_without_words_gives_no_timings(self):
        self.assertEqual(TTSService.estimate_words("...", 0.0, 1.0), [])

    def test_vbee_generation_writes_estimated_words(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        audio = os.path.join(tmp, "shot_01.mp3")
        fake_vbee = mock.Mock()
        fake_vbee.synthesize.side_effect = lambda text, path, voice: open(path, "wb").close()

        with mock.patch.object(VbeeClient, "from_settings", return_value=fake_vbee), \
                mock.patch.object(TTSService, "detect_speech_span", return_value=(0.25, 1.25)), \
                mock.patch.object(TTSService, "get_audio_duration", return_value=1.5):
            duration = TTSService(config_path=SETTINGS, provider="vbee").generate_audio("Đêm tối.", audio)

        self.assertEqual(duration, 1.5)
        fake_vbee.synthesize.assert_called_once_with("Đêm tối.", audio, None)
        self.assertEqual(TTSService.load_words(audio), [
            {"text": "Đêm", "start": 0.25, "end": 0.75},
            {"text": "tối", "start": 0.75, "end": 1.25},
        ])

    @unittest.skipUnless(HAS_FFMPEG, "cần ffmpeg/ffprobe")
    def test_speech_span_skips_leading_and_trailing_silence(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        audio = os.path.join(tmp, "voice.mp3")
        # 0,5 s im lặng + 1 s tiếng + 0,4 s im lặng
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                        "-af", "adelay=500:all=1,apad=pad_dur=0.4", "-ar", "24000", audio], check=True)

        start, end = TTSService.detect_speech_span(audio)
        self.assertAlmostEqual(start, 0.5, delta=0.06)
        self.assertAlmostEqual(end, 1.5, delta=0.06)


@unittest.skipUnless(HAS_FFMPEG, "cần ffmpeg/ffprobe")
class TestDramaticPause(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.out = os.path.join(self.tmp, "pause.mp3")

    def test_synthesize_with_dramatic_pause_shifts_words_and_pads_silence(self):
        tts = TTSService(config_path=SETTINGS)

        def fake_single_audio(text, output_path, voice=None, pitch="+0Hz", rate="+0%"):
            dur = 1.0 if "phần 1" in text else 0.8
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}",
                "-ar", "24000", "-ac", "1", output_path
            ], check=True)
            if "phần 1" in text:
                return [{"text": "phần", "start": 0.1, "end": 0.5}, {"text": "một", "start": 0.5, "end": 0.9}]
            else:
                return [{"text": "phần", "start": 0.1, "end": 0.4}, {"text": "hai", "start": 0.4, "end": 0.7}]

        with mock.patch.object(tts, "generate_single_audio", side_effect=fake_single_audio):
            combined_words = tts._synthesize_with_dramatic_pause(
                segments=["phần 1", "phần 2"],
                output_path=self.out,
                voice="vi-VN-NamMinhNeural",
                pitch="+0Hz",
                rate="+0%",
            )

        self.assertTrue(os.path.exists(self.out))
        total_dur = tts.get_audio_duration(self.out)
        self.assertAlmostEqual(total_dur, 2.7, delta=0.15)

        self.assertEqual(len(combined_words), 4)
        self.assertEqual(combined_words[0]["text"], "phần")
        self.assertAlmostEqual(combined_words[0]["start"], 0.1, delta=0.01)
        self.assertEqual(combined_words[2]["text"], "phần")
        self.assertAlmostEqual(combined_words[2]["start"], 2.0, delta=0.05)
        self.assertEqual(combined_words[3]["text"], "hai")
        self.assertAlmostEqual(combined_words[3]["end"], 2.6, delta=0.05)


if __name__ == "__main__":
    unittest.main()
