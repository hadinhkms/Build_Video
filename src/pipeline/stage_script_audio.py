import json
from typing import Optional

from src.core.models import NarrativeAct, ShotKind, ShotStatus, ShotType, Storyboard
from src.pipeline.context import PipelineContext
from src.pipeline.timing import SHOT_TAIL_PAD_SEC, plan_shot_frames
from src.story_parser import StoryParser
from src.text.alignment import align_word_boundaries_to_raw_text
from src.text.vi_normalizer import VietnameseNormalizer
from src.tts_service import TTSService
from src.vbee_client import VbeeError
from src.visuals.visual_splitter import split_long_shot

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
    print(f" -> Đã tạo {len(sb.shots)} phân cảnh lưu tại: {ctx.storyboard_path}")
    return sb

def run_stage_audio(ctx: PipelineContext) -> Optional[Storyboard]:
    """Tạo giọng đọc TTS & Tách hình cảnh dài."""
    print(f"\n[Stage: audio] 🎙️ Tạo giọng đọc TTS & Tách hình cảnh dài...")
    sb = run_stage_script(ctx)
    if not sb:
        return None

    try:
        tts = TTSService(provider=ctx.tts_provider)
    except (ValueError, VbeeError) as e:
        print(f"[Lỗi] {e}")
        return None

    normalizer = VietnameseNormalizer(pronunciations_path="config/pronunciations.json")
    dramatic_pause = float(ctx.settings.get("audio", {}).get("dramatic_pause_sec", 0.9))

    title_card_idx = next((i for i, s in enumerate(sb.shots) if s.kind == ShotKind.TITLE_CARD), None)
    shot_before_title_card_id = sb.shots[title_card_idx - 1].shot_id if title_card_idx and title_card_idx > 0 else None

    climax_shot_ids = [s.shot_id for s in sb.shots if s.narrative_act == NarrativeAct.CLIMAX and s.kind == ShotKind.STORY]
    last_climax_shot_id = climax_shot_ids[-1] if climax_shot_ids else None

    for idx, shot in enumerate(sb.shots):
        if shot.kind != ShotKind.STORY:
            shot.status = ShotStatus.AUDIO_READY
            continue

        audio_file = f"output/{ctx.chapter_id}/audio/{shot.shot_id}.mp3"
        words_file = f"output/{ctx.chapter_id}/audio/{shot.shot_id}.words.json"

        raw_to_norm = shot.raw_text or shot.voiceover
        norm_res = normalizer.normalize(raw_to_norm)
        shot.voice_text = norm_res.voice_text

        if shot.shot_id == shot_before_title_card_id or shot.shot_id == last_climax_shot_id:
            shot_pad = dramatic_pause
        else:
            shot_pad = SHOT_TAIL_PAD_SEC

        try:
            duration = tts.generate_audio(
                text=shot.voice_text,
                output_path=audio_file,
                speaker=shot.speaker,
                act=shot.narrative_act.value if hasattr(shot.narrative_act, "value") else str(shot.narrative_act),
            )
        except VbeeError as e:
            print(f"[Lỗi] Shot {shot.shot_id}: {e}")
            return None

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
        shot.audio_file = audio_file.replace("\\", "/")
        shot.words_file = words_file.replace("\\", "/")
        shot.status = ShotStatus.AUDIO_READY
        print(f"   Shot {shot.shot_id} [{shot.narrative_act.value}]: duration={shot.duration:.2f}s ({shot.duration_frames}f, pad={shot_pad}s)")

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
                cw_path = f"output/{ctx.chapter_id}/audio/{cs.shot_id}.words.json"
                with open(cw_path, "w", encoding="utf-8") as cwf:
                    json.dump(cw, cwf, ensure_ascii=False, indent=2)
                cs.words_file = cw_path.replace("\\", "/")
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
    print(f" -> Hoàn thành stage audio, tổng số shot sau khi tách: {len(sb.shots)}")
    return sb
