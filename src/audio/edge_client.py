import asyncio
import copy
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from src.audio.audio_utils import boundary_events_to_words, get_audio_duration, get_audio_stream_props

DEFAULT_RETRY_DELAYS: Sequence[float] = (1.5, 3.0, 5.0, 8.0)


def _safe_unlink(path: str) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _unique_tmp_audio_path(output_path: str) -> str:
    p = Path(output_path)
    ext = p.suffix or ".mp3"
    token = f"{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}"
    return str(p.with_name(f".{p.stem}.tmp.{token}{ext}"))


async def _gather_fail_fast(coros: Sequence[Awaitable[Any]]) -> List[Any]:
    """Chạy song song các coroutine; nếu 1 tác vụ lỗi sẽ hủy & đợi các tác vụ còn lại dọn dẹp sạch."""
    tasks = [asyncio.create_task(c) for c in coros]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def _generate_edge_audio_once(
    text: str,
    output_path: str,
    voice: str,
    pitch: str = "+0Hz",
    rate: str = "+0%",
) -> List[Dict[str, Any]]:
    import edge_tts

    parent_dir = os.path.dirname(output_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
        pitch=pitch,
        boundary="WordBoundary",
    )
    events = []
    tmp_path = _unique_tmp_audio_path(output_path)
    try:
        with open(tmp_path, "wb") as audio:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    events.append(chunk)

        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            os.replace(tmp_path, output_path)
        else:
            _safe_unlink(tmp_path)
    except BaseException:
        _safe_unlink(tmp_path)
        raise

    return boundary_events_to_words(events)


async def generate_edge_with_retry_async(
    text: str,
    output_path: str,
    voice: str,
    pitch: str = "+0Hz",
    rate: str = "+0%",
    delays: Optional[Sequence[float]] = None,
    max_attempts: int = 5,
    once_fn: Optional[Callable[..., Awaitable[List[Dict[str, Any]]]]] = None,
) -> List[Dict[str, Any]]:
    """Tổng hợp 1 đoạn Edge-TTS bất đồng bộ với cơ chế retry exponential backoff."""
    retry_delays = list(delays) if delays is not None else list(DEFAULT_RETRY_DELAYS)
    synth_once = once_fn or _generate_edge_audio_once
    parent_dir = os.path.dirname(output_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    last_error: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            words = await synth_once(
                text=text,
                output_path=output_path,
                voice=voice,
                pitch=pitch,
                rate=rate,
            )
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return words
            _safe_unlink(output_path)
            last_error = RuntimeError("Empty audio file generated")
        except asyncio.CancelledError:
            _safe_unlink(output_path)
            raise
        except Exception as e:
            last_error = e
            _safe_unlink(output_path)
        if attempt < max_attempts - 1:
            delay = retry_delays[min(attempt, len(retry_delays) - 1)] if retry_delays else 0.0
            if delay > 0:
                await asyncio.sleep(delay)

    _safe_unlink(output_path)
    raise RuntimeError(
        f"Edge-TTS synthesis failed after {max_attempts} attempts for '{text[:30]}...': {last_error}"
    )


async def generate_edge_batch_async(
    tasks: Sequence[Dict[str, Any]],
    max_concurrency: int = 5,
    retry_fn: Optional[Callable[..., Awaitable[List[Dict[str, Any]]]]] = None,
) -> List[List[Dict[str, Any]]]:
    """Tổng hợp hàng loạt câu Edge-TTS song song có kiểm soát bằng asyncio.Semaphore.

    - Bảo toàn tuyệt đối thứ tự đầu ra khớp thứ tự `tasks`.
    - Các task đã trúng cache (`cached_words` != None hoặc `skip=True`) trả về tức thì
      mà KHÔNG chiếm slot semaphore.
    """
    if not tasks:
        return []

    sem = asyncio.Semaphore(max(1, int(max_concurrency)))
    synth_fn = retry_fn or generate_edge_with_retry_async

    async def _run_one(task: Dict[str, Any]) -> List[Dict[str, Any]]:
        if task.get("skip") or task.get("cached_words") is not None:
            return list(task.get("cached_words") or [])

        out_path = str(task["output_path"])
        parent_dir = os.path.dirname(out_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        async with sem:
            return await synth_fn(
                text=str(task["text"]),
                output_path=out_path,
                voice=str(task["voice"]),
                pitch=str(task.get("pitch", "+0Hz")),
                rate=str(task.get("rate", "+0%")),
            )

    return await _gather_fail_fast([_run_one(t) for t in tasks])


def generate_edge_with_retry(
    text: str,
    output_path: str,
    voice: str,
    pitch: str = "+0Hz",
    rate: str = "+0%",
) -> List[Dict[str, Any]]:
    delays = list(DEFAULT_RETRY_DELAYS)
    max_attempts = 5
    last_error = None
    for attempt in range(max_attempts):
        try:
            words = asyncio.run(
                _generate_edge_audio_once(
                    text=text,
                    output_path=output_path,
                    voice=voice,
                    pitch=pitch,
                    rate=rate,
                )
            )
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return words
            _safe_unlink(output_path)
            last_error = RuntimeError("Empty audio file generated")
        except Exception as e:
            last_error = e
            _safe_unlink(output_path)
        if attempt < max_attempts - 1:
            time.sleep(delays[attempt])

    _safe_unlink(output_path)
    raise RuntimeError(f"Edge-TTS synthesis failed after {max_attempts} attempts for '{text[:30]}...': {last_error}")


def _concat_segments_with_silence(
    seg_files: List[Path],
    seg_words_list: List[List[Dict[str, Any]]],
    output_path: str,
    dramatic_pause_sec: float,
    temp_dir: Path,
) -> List[Dict[str, Any]]:
    """Ghép các tệp đoạn âm thanh kèm khoảng lặng dramatic_pause_sec bằng ffmpeg (blocking I/O)."""
    part_files: List[str] = []
    combined_words: List[Dict[str, Any]] = []
    curr_offset = 0.0

    for idx, (seg_out, seg_words) in enumerate(zip(seg_files, seg_words_list)):
        dur = get_audio_duration(str(seg_out))

        for w in seg_words:
            shifted = copy.deepcopy(w)
            shifted["start"] = round(w["start"] + curr_offset, 4)
            shifted["end"] = round(w["end"] + curr_offset, 4)
            combined_words.append(shifted)

        part_files.append(str(seg_out))
        curr_offset += dur

        if idx < len(seg_files) - 1:
            sr, cl = get_audio_stream_props(str(seg_out))
            silence_file = temp_dir / f"silence_{idx}.mp3"
            cmd_silence = [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", f"anullsrc=r={sr}:cl={cl}",
                "-t", str(dramatic_pause_sec),
                "-c:a", "libmp3lame",
                str(silence_file),
            ]
            subprocess.run(cmd_silence, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            part_files.append(str(silence_file))
            curr_offset += dramatic_pause_sec

    concat_list = temp_dir / "concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for pf in part_files:
            clean_p = pf.replace("\\", "/")
            f.write(f"file '{clean_p}'\n")

    parent_dir = os.path.dirname(output_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    tmp_out = _unique_tmp_audio_path(output_path)
    cmd_concat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        tmp_out,
    ]
    try:
        subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if not os.path.exists(tmp_out) or os.path.getsize(tmp_out) <= 0:
            raise RuntimeError(f"Empty concatenated audio generated: {output_path}")
        os.replace(tmp_out, output_path)
    except BaseException:
        _safe_unlink(tmp_out)
        raise
    return combined_words


async def synthesize_with_dramatic_pause_async(
    segments: List[str],
    output_path: str,
    voice: str,
    pitch: str,
    rate: str,
    dramatic_pause_sec: float,
    sem: Optional[asyncio.Semaphore] = None,
    single_async_fn: Optional[Callable[..., Awaitable[List[Dict[str, Any]]]]] = None,
) -> List[Dict[str, Any]]:
    """Tổng hợp song song từng đoạn phân tách bởi `...` rồi ghép khoảng lặng FFmpeg trong asyncio.to_thread()."""
    temp_dir = Path(tempfile.mkdtemp())
    synth_fn = single_async_fn or generate_edge_with_retry_async

    async def _synth_seg(idx: int, seg_text: str) -> List[Dict[str, Any]]:
        seg_out = temp_dir / f"seg_{idx}.mp3"
        if sem is not None:
            async with sem:
                return await synth_fn(
                    text=seg_text,
                    output_path=str(seg_out),
                    voice=voice,
                    pitch=pitch,
                    rate=rate,
                )
        return await synth_fn(
            text=seg_text,
            output_path=str(seg_out),
            voice=voice,
            pitch=pitch,
            rate=rate,
        )

    try:
        seg_files = [temp_dir / f"seg_{idx}.mp3" for idx in range(len(segments))]
        seg_words_list = await _gather_fail_fast(
            [_synth_seg(idx, seg) for idx, seg in enumerate(segments)]
        )
        return await asyncio.to_thread(
            _concat_segments_with_silence,
            seg_files,
            seg_words_list,
            output_path,
            dramatic_pause_sec,
            temp_dir,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def synthesize_with_dramatic_pause(
    segments: List[str],
    output_path: str,
    voice: str,
    pitch: str,
    rate: str,
    dramatic_pause_sec: float,
    single_audio_fn: Callable,
) -> List[Dict[str, Any]]:
    """Ghép các đoạn phân tách bởi `...` với khoảng lặng dramatic_pause_sec bằng ffmpeg."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        seg_files: List[Path] = []
        seg_words_list: List[List[Dict[str, Any]]] = []
        for idx, seg in enumerate(segments):
            seg_out = temp_dir / f"seg_{idx}.mp3"
            seg_words = single_audio_fn(
                text=seg,
                output_path=str(seg_out),
                voice=voice,
                pitch=pitch,
                rate=rate,
            )
            seg_files.append(seg_out)
            seg_words_list.append(seg_words)

        return _concat_segments_with_silence(
            seg_files=seg_files,
            seg_words_list=seg_words_list,
            output_path=output_path,
            dramatic_pause_sec=dramatic_pause_sec,
            temp_dir=temp_dir,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
