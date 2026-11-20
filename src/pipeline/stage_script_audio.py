import hashlib
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.models import NarrativeAct, ShotKind, ShotStatus, ShotType, Storyboard
from src.pipeline.context import PipelineContext
from src.pipeline.timing import SHOT_TAIL_PAD_SEC, plan_shot_frames
from src.story_parser import StoryParser
from src.text.alignment import align_word_boundaries_to_raw_text
from src.text.vi_normalizer import VietnameseNormalizer
from src.tts_service import TTSService
from src.vbee_client import VbeeError
from src.visuals.visual_splitter import split_long_shot

SCRIPT_SIGNATURE_FILENAME = ".script_signature.json"
_SCRIPT_CONFIG_FILES = (
    "config/story_rules.json",
    "config/characters.json",
    "config/environments.json",
    "config/settings.json",
)


def _compute_config_signature(ctx: PipelineContext) -> str:
    """Tính SHA1 tổng hợp các tệp cấu hình ảnh hưởng trực tiếp tới StoryParser (story_rules, characters, environments, settings)."""
    hasher = hashlib.sha1()
    for rel_path in _SCRIPT_CONFIG_FILES:
        p = Path(rel_path)
        hasher.update(rel_path.encode("utf-8"))
        hasher.update(b"\0")
        if p.exists():
            try:
                with open(p, "rb") as f:
                    while chunk := f.read(65536):
                        hasher.update(chunk)
            except OSError:
                pass
        hasher.update(b"\0")
    try:
        ctx_blob = json.dumps(
            {"story_rules": ctx.story_rules, "settings": ctx.settings},
            sort_keys=True,
            ensure_ascii=False,
        )
        hasher.update(ctx_blob.encode("utf-8"))
    except Exception:
        pass
    return hasher.hexdigest()


def _compute_input_signature(ctx: PipelineContext) -> Dict[str, Any]:
    chapter_path = Path(ctx.chapter_file)
    sha1 = ""
    if chapter_path.exists():
        hasher = hashlib.sha1()
        with open(chapter_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        sha1 = hasher.hexdigest()
    return {
        "chapter_file": str(chapter_path.resolve()) if chapter_path.exists() else str(ctx.chapter_file),
        "source_sha1": sha1,
        "config_sha1": _compute_config_signature(ctx),
        "title": ctx.title,
        "env": ctx.env,
    }


def _write_script_signature(ctx: PipelineContext, stage_state: str) -> None:
    sig_path = ctx.chapter_dir / SCRIPT_SIGNATURE_FILENAME
    payload = {**_compute_input_signature(ctx), "stage_state": stage_state}
    token = f"{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}"
    tmp_path = sig_path.with_name(f".{sig_path.name}.tmp.{token}")
    try:
        sig_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(str(tmp_path), str(sig_path))
    except OSError:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def _try_load_fresh_script_storyboard(ctx: PipelineContext) -> Optional[Storyboard]:
    """Tái dùng storyboard vừa được `run_stage_script()` tạo ra nếu cùng dấu vết input/config và chưa qua stage audio."""
    sig_path = ctx.chapter_dir / SCRIPT_SIGNATURE_FILENAME
    if not ctx.storyboard_path.exists() or not sig_path.exists():
        return None
    try:
        with open(sig_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
    except Exception:
        return None

    if saved.get("stage_state") != "script_fresh":
        return None

    current = _compute_input_signature(ctx)
    if not current["source_sha1"]:
        return None
    for key in ("chapter_file", "source_sha1", "config_sha1", "title", "env"):
        if saved.get(key) != current.get(key):
            return None

    sb = ctx.state_mgr.load_state()
    if not sb or not sb.shots:
        return None
    # Không tái dùng nếu storyboard đã chứa cảnh con tách hình từ lần chạy audio trước
    if any(getattr(s, "parent_id", None) for s in sb.shots):
        return None
    return sb


def run_stage_script(ctx: PipelineContext) -> Optional[Storyboard]:
    """Bóc tách kịch bản phân cảnh cho chương truyện."""
    print(f"\n[Stage: script] 📜 Bóc tách kịch bản phân cảnh cho chương: '{ctx.chapter_id}'...")
    with open(ctx.chapter_file, "r", encoding="utf-8") as f:
        content = f.read()

    parser = StoryParser()
    sb = parser.parse_chapter_to_storyboard(
        content,
        title=ctx.title,
        default_env=ctx.env,
        chapter_filename=ctx.chapter_file,
    )
    ctx.state_mgr.save_state(sb)
    _write_script_signature(ctx, stage_state="script_fresh")
    print(f" -> Đã tạo {len(sb.shots)} phân cảnh lưu tại: {ctx.storyboard_path}")
    return sb


def run_stage_audio(ctx: PipelineContext) -> Optional[Storyboard]:
    """Tạo giọng đọc TTS song song có kiểm soát & Tách hình cảnh dài."""
    print(f"\n[Stage: audio] 🎙️ Tạo giọng đọc TTS & Tách hình cảnh dài...")
    sb = _try_load_fresh_script_storyboard(ctx)
    if sb is not None:
        print(f" -> Tái sử dụng storyboard mới bóc tách ({len(sb.shots)} phân cảnh, bỏ qua re-parse thừa).")
    else:
        sb = run_stage_script(ctx)
    if not sb:
        return None

    try:
        tts = TTSService(provider=ctx.tts_provider)
    except (ValueError, VbeeError) as e:
        print(f"[Lỗi] {e}")
        return None

    normalizer = VietnameseNormalizer(pronunciations_path="config/pronunciations.json")
    audio_cfg = ctx.settings.get("audio", {})
    dramatic_pause = float(audio_cfg.get("dramatic_pause_sec", 0.9))
    cfg_concurrency = int(audio_cfg.get("tts_concurrency", 5))
    effective_concurrency = tts.resolve_effective_concurrency(cfg_concurrency)

    title_card_idx = next((i for i, s in enumerate(sb.shots) if s.kind == ShotKind.TITLE_CARD), None)
    shot_before_title_card_id = sb.shots[title_card_idx - 1].shot_id if title_card_idx and title_card_idx > 0 else None

    climax_shot_ids = [s.shot_id for s in sb.shots if s.narrative_act == NarrativeAct.CLIMAX and s.kind == ShotKind.STORY]
    last_climax_shot_id = climax_shot_ids[-1] if climax_shot_ids else None

    ctx.audio_dir.mkdir(parents=True, exist_ok=True)

    # 1. Chuẩn hóa văn bản & gom tác vụ TTS theo đúng thứ tự sb.shots
    story_records: List[Tuple[Any, Any, str, str, float]] = []
    batch_tasks: List[Dict[str, Any]] = []

    for shot in sb.shots:
        if shot.kind != ShotKind.STORY:
            shot.status = ShotStatus.AUDIO_READY
            continue

        audio_file = (ctx.audio_dir / f"{shot.shot_id}.mp3").as_posix()
        words_file = (ctx.audio_dir / f"{shot.shot_id}.words.json").as_posix()

        raw_to_norm = shot.raw_text or shot.voiceover
        norm_res = normalizer.normalize(raw_to_norm)
        shot.voice_text = norm_res.voice_text

        if shot.shot_id == shot_before_title_card_id or shot.shot_id == last_climax_shot_id:
            shot_pad = dramatic_pause
        else:
            shot_pad = SHOT_TAIL_PAD_SEC

        act_val = shot.narrative_act.value if hasattr(shot.narrative_act, "value") else str(shot.narrative_act)
        story_records.append((shot, norm_res, audio_file, words_file, shot_pad))
        batch_tasks.append({
            "shot_id": shot.shot_id,
            "text": shot.voice_text,
            "output_path": audio_file,
            "speaker": shot.speaker,
            "act": act_val,
        })

    # 2. Thực thi TTS song song theo semaphore (cache hit không chiếm slot)
    if batch_tasks:
        print(
            f" -> Tổng hợp {len(batch_tasks)} câu thoại "
            f"(provider={tts.provider}, concurrency={effective_concurrency})..."
        )
        try:
            durations = tts.generate_audio_batch(
                batch_tasks,
                max_concurrency=effective_concurrency,
            )
        except (VbeeError, RuntimeError) as e:
            print(f"[Lỗi] Tổng hợp TTS ({tts.provider}) thất bại: {e}")
            return None

        # 3. Căn chỉnh word boundaries & cập nhật thông số shot theo đúng thứ tự gốc
        for (shot, norm_res, audio_file, words_file, shot_pad), duration in zip(story_records, durations):
            raw_wb = TTSService.load_words(audio_file)
            aligned_words = align_word_boundaries_to_raw_text(
                raw_text=shot.raw_text,
                voice_text=shot.voice_text,
                spans=norm_res.spans,
                wb_events=raw_wb,
            )
            with open(words_file, "w", encoding="utf-8") as wf:
                json.dump(aligned_words, wf, ensure_ascii=False, indent=2)

            shot.duration_frames = plan_shot_frames(duration, ctx.fps, ctx.shot_min, pad_sec=shot_pad)
            shot.duration = round(shot.duration_frames / ctx.fps, 4)
            shot.audio_file = audio_file
            shot.words_file = words_file
            shot.status = ShotStatus.AUDIO_READY
            act_label = shot.narrative_act.value if hasattr(shot.narrative_act, "value") else str(shot.narrative_act)
            print(f"   Shot {shot.shot_id} [{act_label}]: duration={shot.duration:.2f}s ({shot.duration_frames}f, pad={shot_pad}s)")

    # Tách hình cho các cảnh story dài > shot_max
    new_shots = []
    shot_max_frames = round(ctx.shot_max * ctx.fps)
    for shot in sb.shots:
        if shot.kind == ShotKind.STORY and shot.duration_frames > shot_max_frames:
            words = TTSService.load_words(shot.audio_file)
            child_shots, child_words = split_long_shot(
                shot=shot,
                words=words,
                fps=ctx.fps,
                shot_max_sec=ctx.shot_max,
                split_min_sec=ctx.split_min,
                phrase_starters=ctx.story_rules.get("phrase_starters", []),
            )
            print(f"   ✂️ Shot {shot.shot_id} ({shot.duration:.2f}s > {ctx.shot_max}s) được tách hình thành {len(child_shots)} cảnh con:")
            for cs, cw in zip(child_shots, child_words):
                cw_path = (ctx.audio_dir / f"{cs.shot_id}.words.json").as_posix()
                with open(cw_path, "w", encoding="utf-8") as cwf:
                    json.dump(cw, cwf, ensure_ascii=False, indent=2)
                cs.words_file = cw_path
                new_shots.append(cs)
                print(f"      -> {cs.shot_id}: {cs.duration:.2f}s ({cs.duration_frames}f, type={cs.shot_type}, offset={cs.audio_start_in_file_sec:.2f}s)")
        else:
            new_shots.append(shot)

    # Cỡ cảnh không trùng
    shot_priority_by_act = {
        NarrativeAct.HOOK: [ShotType.CLOSEUP, ShotType.EXTREME_CLOSEUP],
        NarrativeAct.SETUP: [ShotType.WIDE, ShotType.MEDIUM],
        NarrativeAct.RISING: [ShotType.MEDIUM, ShotType.OVER_SHOULDER],
        NarrativeAct.CLIMAX: [ShotType.CLOSEUP, ShotType.EXTREME_CLOSEUP],
        NarrativeAct.CLIFFHANGER: [ShotType.EXTREME_CLOSEUP, ShotType.CLOSEUP, ShotType.MEDIUM],
    }
    prev_type = None
    for s in new_shots:
        if s.kind == ShotKind.STORY:
            priorities = shot_priority_by_act.get(s.narrative_act, [ShotType.MEDIUM, ShotType.CLOSEUP])
            chosen = priorities[0].value
            if prev_type and chosen == prev_type:
                for cand in priorities[1:]:
                    if cand.value != prev_type:
                        chosen = cand.value
                        break
            s.shot_type = chosen
            prev_type = chosen

    sb.shots = new_shots
    sb.total_duration = sum(s.duration for s in sb.shots)
    ctx.state_mgr.save_state(sb)
    _write_script_signature(ctx, stage_state="audio_done")
    print(f" -> Hoàn thành stage audio, tổng số shot sau khi tách: {len(sb.shots)}")
    return sb
