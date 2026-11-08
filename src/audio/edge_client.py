import asyncio
import copy
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from src.audio.audio_utils import boundary_events_to_words, get_audio_duration, get_audio_stream_props


async def _generate_edge_audio_once(
    text: str,
    output_path: str,
    voice: str,
    pitch: str = "+0Hz",
    rate: str = "+0%",
) -> List[Dict[str, any]]:
    import edge_tts

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
        pitch=pitch,
        boundary="WordBoundary",
    )
    events = []
    with open(output_path, "wb") as audio:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                events.append(chunk)

    return boundary_events_to_words(events)


def generate_edge_with_retry(
    text: str,
    output_path: str,
    voice: str,
    pitch: str = "+0Hz",
    rate: str = "+0%",
) -> List[Dict[str, any]]:
    delays = [1.5, 3.0, 5.0, 8.0]
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
        except Exception as e:
            last_error = e
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            if attempt < max_attempts - 1:
                time.sleep(delays[attempt])

    raise RuntimeError(f"Edge-TTS synthesis failed after {max_attempts} attempts for '{text[:30]}...': {last_error}")


def synthesize_with_dramatic_pause(
    segments: List[str],
    output_path: str,
    voice: str,
    pitch: str,
    rate: str,
    dramatic_pause_sec: float,
    single_audio_fn: Callable,
) -> List[Dict[str, any]]:
    """Ghép các đoạn phân tách bởi `...` với khoảng lặng dramatic_pause_sec bằng ffmpeg."""
    temp_dir = Path(tempfile.mkdtemp())
    part_files = []
    combined_words = []
    curr_offset = 0.0

    try:
        for idx, seg in enumerate(segments):
            seg_out = temp_dir / f"seg_{idx}.mp3"
            seg_words = single_audio_fn(
                text=seg,
                output_path=str(seg_out),
                voice=voice,
                pitch=pitch,
                rate=rate,
            )
            dur = get_audio_duration(str(seg_out))

            for w in seg_words:
                shifted = copy.deepcopy(w)
                shifted["start"] = round(w["start"] + curr_offset, 4)
                shifted["end"] = round(w["end"] + curr_offset, 4)
                combined_words.append(shifted)

            part_files.append(str(seg_out))
            curr_offset += dur

            if idx < len(segments) - 1:
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

        cmd_concat = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            output_path,
        ]
        subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    finally:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    return combined_words
