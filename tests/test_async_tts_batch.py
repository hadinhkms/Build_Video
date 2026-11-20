import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from src.audio.edge_client import (
    generate_edge_batch_async,
    generate_edge_with_retry_async,
    synthesize_with_dramatic_pause_async,
)
from src.core.models import NarrativeAct, ShotKind
from src.core.state_manager import StateManager
from src.pipeline.context import PipelineContext
from src.pipeline.stage_script_audio import run_stage_audio, run_stage_script
from src.story_parser import StoryParser
from src.tts_service import TTSService

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / "config" / "settings.json"
HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


class TestAsyncEdgeBatch(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_generate_edge_batch_async_caps_concurrency_preserves_order_and_skips_cache(self):
        active = 0
        peak = 0
        called_texts = []

        async def fake_synth(text, output_path, voice, pitch="+0Hz", rate="+0%"):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            called_texts.append(text)
            # Đảo ngược độ trễ để kiểm chứng thứ tự đầu ra không bị xáo trộn
            idx = int(text.split("_")[-1])
            await asyncio.sleep(0.015 * (10 - idx))
            Path(output_path).write_bytes(b"FAKE_MP3")
            active -= 1
            return [{"text": text, "start": 0.0, "end": 0.5}]

        tasks = []
        for i in range(10):
            t = {
                "text": f"cau_{i}",
                "output_path": str(self.tmp / f"shot_{i:02d}.mp3"),
                "voice": "vi-VN-NamMinhNeural",
            }
            if i in (2, 7):
                # Giả lập 2 câu trúng cache -> không chiếm slot semaphore
                t["cached_words"] = [{"text": f"cached_{i}", "start": 0.0, "end": 0.3}]
            tasks.append(t)

        t0 = time.perf_counter()
        results = asyncio.run(
            generate_edge_batch_async(tasks, max_concurrency=4, retry_fn=fake_synth)
        )
        elapsed = time.perf_counter() - t0

        self.assertLessEqual(peak, 4)
        self.assertGreaterEqual(peak, 2)
        self.assertEqual(len(called_texts), 8)  # 2 câu cache không gọi synth
        self.assertEqual(len(results), 10)
        for i in range(10):
            expected_txt = f"cached_{i}" if i in (2, 7) else f"cau_{i}"
            self.assertEqual(results[i][0]["text"], expected_txt)
        # Chạy song song 4 luồng phải nhanh hơn tổng thời gian tuần tự đáng kể
        self.assertLess(elapsed, 0.5)

    def test_generate_edge_with_retry_async_retries_and_cleans_partial_file(self):
        out = self.tmp / "retry_shot.mp3"
        attempts = {"n": 0}

        async def flaky_once(text, output_path, voice, pitch, rate):
            attempts["n"] += 1
            if attempts["n"] < 3:
                Path(output_path).write_bytes(b"PARTIAL")
                raise ConnectionError("network drop")
            Path(output_path).write_bytes(b"VALID_MP3_DATA")
            return [{"text": "ok", "start": 0.0, "end": 0.4}]

        words = asyncio.run(
            generate_edge_with_retry_async(
                text="Thử retry",
                output_path=str(out),
                voice="vi-VN-NamMinhNeural",
                delays=[0.0, 0.0],
                max_attempts=4,
                once_fn=flaky_once,
            )
        )
        self.assertEqual(attempts["n"], 3)
        self.assertEqual(words[0]["text"], "ok")
        self.assertEqual(out.read_bytes(), b"VALID_MP3_DATA")

    def test_tts_service_batch_cache_hit_does_not_occupy_semaphore_and_caps_vbee(self):
        tts = TTSService(config_path=str(SETTINGS_PATH), provider="edge")
        self.assertEqual(tts.resolve_effective_concurrency(5), 5)

        with mock.patch.dict(os.environ, {"VBEE_APP_ID": "a", "VBEE_ACCESS_TOKEN": "t"}), \
             mock.patch("dotenv.load_dotenv"):
            tts_vbee = TTSService(config_path=str(SETTINGS_PATH), provider="vbee")
            self.assertEqual(tts_vbee.resolve_effective_concurrency(10), 2)
            self.assertEqual(tts_vbee.resolve_effective_concurrency(1), 1)

        # Tạo sẵn 2 tệp trúng cache SHA1
        cached_indices = {1, 4}
        batch = []
        for i in range(6):
            out = str(self.tmp / f"batch_{i}.mp3")
            text = f"Câu thoại số {i}."
            batch.append({"text": text, "output_path": out, "speaker": "narrator", "act": "SETUP"})
            if i in cached_indices:
                v, p, r = tts.get_speaker_voice_params("narrator", "SETUP")
                ckey = tts.compute_cache_key(text, v, p, r)
                Path(out).write_bytes(b"CACHED_MP3")
                Path(tts.words_path_for(out)).write_text(
                    json.dumps([{"text": f"cached_{i}", "start": 0.0, "end": 1.0}]),
                    encoding="utf-8",
                )
                Path(tts.meta_path_for(out)).write_text(
                    json.dumps({"cache_key": ckey}),
                    encoding="utf-8",
                )

        synth_calls = []

        async def fake_edge_async(text, output_path, voice, pitch, rate):
            synth_calls.append(text)
            await asyncio.sleep(0.02)
            Path(output_path).write_bytes(b"FRESH_MP3")
            return [{"text": text, "start": 0.0, "end": 1.2}]

        with mock.patch.object(tts, "_generate_edge_with_retry_async", side_effect=fake_edge_async), \
             mock.patch.object(tts, "get_audio_duration", side_effect=lambda p: 2.0 + int(Path(p).stem.split("_")[1])):
            durations = tts.generate_audio_batch(batch, max_concurrency=3)

        self.assertEqual(len(synth_calls), 4)  # 6 - 2 cached = 4
        self.assertEqual(durations, [2.0, 3.0, 4.0, 5.0, 6.0, 7.0])

    @unittest.skipUnless(HAS_FFMPEG, "cần ffmpeg/ffprobe")
    def test_dramatic_pause_async_synthesizes_segments_and_concats_via_to_thread(self):
        out = self.tmp / "pause_async.mp3"

        async def fake_seg(text, output_path, voice, pitch, rate):
            dur = 0.8 if "một" in text else 0.6
            await asyncio.to_thread(
                subprocess.run,
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}",
                    "-ar", "24000", "-ac", "1", output_path,
                ],
                check=True,
            )
            return [{"text": text, "start": 0.05, "end": dur - 0.05}]

        sem = asyncio.Semaphore(3)
        words = asyncio.run(
            synthesize_with_dramatic_pause_async(
                segments=["Đoạn một", "Đoạn hai"],
                output_path=str(out),
                voice="vi-VN-NamMinhNeural",
                pitch="+0Hz",
                rate="+0%",
                dramatic_pause_sec=0.5,
                sem=sem,
                single_async_fn=fake_seg,
            )
        )
        self.assertTrue(out.exists())
        self.assertEqual(len(words), 2)
        self.assertEqual(words[0]["text"], "Đoạn một")
        self.assertEqual(words[1]["text"], "Đoạn hai")
        self.assertGreater(words[1]["start"], 1.1)  # 0.8s + 0.5s pause

    def test_stage_audio_skips_duplicate_script_parse_but_reparses_on_input_change(self):
        chapter_txt = self.tmp / "demo_ch.txt"
        chapter_txt.write_text(
            "Chương 1: Đêm Mưa\n\n"
            "[HOOK]\nĐêm đó mưa rơi không ngớt ngoài khung cửa sổ.\n\n"
            "[SETUP]\nNam ngồi lặng lẽ trước bàn làm việc cũ kỹ.\n"
            "Ánh đèn vàng hắt dài trên sàn gỗ ẩm ướt.\n",
            encoding="utf-8",
        )
        chapter_dir = self.tmp / "out_demo"
        audio_dir = chapter_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        sb_path = chapter_dir / "storyboard.json"

        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            settings = json.load(f)
        with open(ROOT / "config" / "story_rules.json", "r", encoding="utf-8") as f:
            story_rules = json.load(f)

        def make_ctx(title=None):
            return PipelineContext(
                chapter_file=str(chapter_txt),
                output_name="final.mp4",
                tts_provider="edge",
                renderer="remotion",
                stage="all",
                title=title,
                env=None,
                frames=None,
                bench=None,
                settings=settings,
                story_rules=story_rules,
                fps=24,
                shot_min=4.0,
                shot_max=6.5,
                split_min=2.5,
                chapter_id="demo_ch",
                chapter_dir=chapter_dir,
                audio_dir=audio_dir,
                storyboard_path=sb_path,
                state_mgr=StateManager(str(sb_path)),
            )

        def fake_batch(self_tts, tasks, max_concurrency=None):
            durs = []
            for t in tasks:
                out_p = Path(t["output_path"])
                out_p.parent.mkdir(parents=True, exist_ok=True)
                out_p.write_bytes(b"MP3")
                words = [
                    {"text": w, "start": round(i * 0.25, 3), "end": round((i + 1) * 0.25, 3)}
                    for i, w in enumerate(t["text"].split())
                ]
                Path(TTSService.words_path_for(str(out_p))).write_text(
                    json.dumps(words, ensure_ascii=False), encoding="utf-8"
                )
                durs.append(3.8)
            return durs

        ctx = make_ctx()
        with mock.patch.object(
            StoryParser, "parse_chapter_to_storyboard", wraps=StoryParser().parse_chapter_to_storyboard
        ) as spy_parse, mock.patch.object(
            TTSService, "generate_audio_batch", autospec=True, side_effect=fake_batch
        ):
            # 1. Chạy script rồi audio liên tiếp (giống --stage all / --stage prepare)
            sb1 = run_stage_script(ctx)
            self.assertIsNotNone(sb1)
            sb2 = run_stage_audio(ctx)
            self.assertIsNotNone(sb2)
            # StoryParser chỉ được gọi ĐÚNG 1 LẦN (không re-parse thừa ở stage audio!)
            self.assertEqual(spy_parse.call_count, 1)

            # Kiểm tra quy tắc cỡ cảnh không trùng giữa các STORY shot liên tiếp
            story_types = [s.shot_type for s in sb2.shots if s.kind == ShotKind.STORY]
            for prev_t, curr_t in zip(story_types, story_types[1:]):
                self.assertNotEqual(prev_t, curr_t)

            # 2. Sửa nội dung file .txt rồi gọi thẳng run_stage_audio -> PHẢI re-parse
            chapter_txt.write_text(
                chapter_txt.read_text(encoding="utf-8") + "\n[CLIMAX]\nTiếng bước chân vang lên sau cánh cửa!\n",
                encoding="utf-8",
            )
            sb3 = run_stage_audio(ctx)
            self.assertIsNotNone(sb3)
            self.assertEqual(spy_parse.call_count, 2)
            self.assertGreater(len(sb3.shots), len(sb2.shots))

            # 3. Gọi run_stage_audio lần 2 liên tiếp (sau audio_done) -> PHẢI re-parse để tránh tách cảnh lặp
            sb4 = run_stage_audio(ctx)
            self.assertIsNotNone(sb4)
            self.assertEqual(spy_parse.call_count, 3)
            self.assertEqual(len(sb4.shots), len(sb3.shots))

            # 4. Chạy script, sau đó đổi ctx.story_rules (hoặc title/env) rồi chạy audio -> PHẢI re-parse
            run_stage_script(ctx)
            self.assertEqual(spy_parse.call_count, 4)
            ctx_modified_rules = make_ctx(title=None)
            ctx_modified_rules.story_rules = {**story_rules, "phrase_starters": ["nhưng", "tuy nhiên"]}
            sb5 = run_stage_audio(ctx_modified_rules)
            self.assertIsNotNone(sb5)
            self.assertEqual(spy_parse.call_count, 5)

            # 5. Đổi title sau run_stage_script -> PHẢI re-parse
            run_stage_script(ctx)
            self.assertEqual(spy_parse.call_count, 6)
            ctx_new_title = make_ctx(title="Tiêu đề mới")
            sb6 = run_stage_audio(ctx_new_title)
            self.assertIsNotNone(sb6)
            self.assertEqual(spy_parse.call_count, 7)

    def test_generate_audio_batch_works_inside_running_event_loop(self):
        tts = TTSService(config_path=str(SETTINGS_PATH), provider="edge")
        tasks = [
            {"text": f"Câu {i}", "output_path": str(self.tmp / f"loop_{i}.mp3"), "speaker": "narrator"}
            for i in range(3)
        ]

        async def fake_edge_async(text, output_path, voice, pitch, rate):
            Path(output_path).write_bytes(b"LOOP_MP3")
            return [{"text": text, "start": 0.0, "end": 0.5}]

        async def caller_in_running_loop():
            # Gọi wrapper đồng bộ generate_audio_batch ngay bên trong event loop đang chạy
            return tts.generate_audio_batch(tasks, max_concurrency=2)

        with mock.patch.object(tts, "_generate_edge_with_retry_async", side_effect=fake_edge_async), \
             mock.patch.object(tts, "get_audio_duration", return_value=1.5):
            durations = asyncio.run(caller_in_running_loop())

        self.assertEqual(durations, [1.5, 1.5, 1.5])
        for i in range(3):
            self.assertTrue((self.tmp / f"loop_{i}.mp3").exists())

    def test_batch_failure_cleans_empty_or_cancelled_files_and_stage_audio_returns_none(self):
        # 1. File 0-byte không được để sót sau khi retry thất bại
        empty_out = self.tmp / "empty_fail.mp3"

        async def empty_once(text, output_path, voice, pitch, rate):
            Path(output_path).write_bytes(b"")
            return []

        with self.assertRaises(RuntimeError):
            asyncio.run(
                generate_edge_with_retry_async(
                    text="Rỗng",
                    output_path=str(empty_out),
                    voice="vi-VN-NamMinhNeural",
                    delays=[0.0],
                    max_attempts=2,
                    once_fn=empty_once,
                )
            )
        self.assertFalse(empty_out.exists(), "Không được để lại tệp .mp3 0-byte khi tổng hợp thất bại!")

        # 2. Khi 1 câu trong batch ném RuntimeError -> hủy sạch tác vụ anh em & không để sót file dở dang
        tts = TTSService(config_path=str(SETTINGS_PATH), provider="edge")
        out_ok = self.tmp / "cancel_sibling.mp3"
        out_fail = self.tmp / "fail_item.mp3"

        async def mixed_edge_async(text, output_path, voice, pitch, rate):
            if "lỗi" in text:
                Path(output_path).write_bytes(b"PARTIAL_FAIL")
                raise RuntimeError("Edge WebSocket closed")
            Path(output_path).write_bytes(b"PARTIAL_INFLIGHT")
            try:
                await asyncio.sleep(5.0)
            except asyncio.CancelledError:
                raise
            return [{"text": text, "start": 0.0, "end": 0.5}]

        with mock.patch.object(tts, "_generate_edge_with_retry_async", side_effect=mixed_edge_async):
            with self.assertRaises(RuntimeError):
                tts.generate_audio_batch(
                    [
                        {"text": "Câu đang stream", "output_path": str(out_ok)},
                        {"text": "Câu gây lỗi", "output_path": str(out_fail)},
                    ],
                    max_concurrency=2,
                )
        self.assertFalse(out_fail.exists(), "Tệp của câu lỗi phải bị xóa sạch!")
        self.assertFalse(out_ok.exists(), "Tệp dở dang của tác vụ anh em bị hủy phải bị xóa sạch!")

        # 3. run_stage_audio trả về None sạch khi batch ném RuntimeError hoặc VbeeError
        from src.vbee_client import VbeeError

        chapter_txt = self.tmp / "err_ch.txt"
        chapter_txt.write_text("[HOOK]\nMột câu thử lỗi.\n", encoding="utf-8")
        chapter_dir = self.tmp / "out_err"
        audio_dir = chapter_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        sb_path = chapter_dir / "storyboard.json"
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        story_rules = json.loads((ROOT / "config" / "story_rules.json").read_text(encoding="utf-8"))
        ctx = PipelineContext(
            chapter_file=str(chapter_txt),
            output_name="final.mp4",
            tts_provider="edge",
            renderer="remotion",
            stage="audio",
            title=None,
            env=None,
            frames=None,
            bench=None,
            settings=settings,
            story_rules=story_rules,
            fps=24,
            shot_min=4.0,
            shot_max=6.5,
            split_min=2.5,
            chapter_id="err_ch",
            chapter_dir=chapter_dir,
            audio_dir=audio_dir,
            storyboard_path=sb_path,
            state_mgr=StateManager(str(sb_path)),
        )
        for err in (RuntimeError("edge failed"), VbeeError("vbee failed")):
            with mock.patch.object(TTSService, "generate_audio_batch", side_effect=err):
                res = run_stage_audio(ctx)
            self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()
