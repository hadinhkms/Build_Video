import json
import os
from pathlib import Path

from src.export.remotion_props import RemotionPropsExporter
from src.pipeline.context import PipelineContext
from src.visuals.asset_check import AssetChecker
from src.visuals.asset_packager import AssetPackager
from src.visuals.cutout import process_all_characters
from src.visuals.stills_generator import StillsGenerator

def run_stage_assets(ctx: PipelineContext) -> bool:
    """Chuẩn bị tài sản ảnh, gói prompt và kiểm tra raccord."""
    print(f"\n[Stage: assets] 🎨 Chuẩn bị tài sản ảnh, gói prompt và kiểm tra raccord...")
    sb = ctx.state_mgr.load_state()
    if not sb:
        print("[Lỗi] Không tìm thấy storyboard. Vui lòng chạy stage script và audio trước.")
        return False

    packager = AssetPackager()
    pkg_dir = packager.export_package(ctx.chapter_id)
    print(f" -> Đã xuất gói prompt tạo ảnh tại: {pkg_dir}")

    cutout_results = process_all_characters(Path("assets"))
    if cutout_results:
        print(f" -> Đã xử lý tách nền cho {len(cutout_results)} nhân vật: {list(cutout_results.keys())}")

    checker = AssetChecker()
    checklist = checker.check_and_assign_visuals(sb)

    if checklist["downgraded_shots"]:
        print(" -> Hạ cấp over_shoulder để đảm bảo raccord:")
        for log in checklist["downgraded_shots"]:
            print(f"    * {log}")

    if checklist["warnings"]:
        print(" -> Cảnh báo kiểm tra tài sản:")
        for w in checklist["warnings"]:
            print(f"    * {w}")

    print(f" -> Thống kê chế độ visual: {checklist['stats']}")
    if checklist["missing_plates"]:
        print(f" -> [Thiếu Plate] Chưa có ảnh bối cảnh cho: {checklist['missing_plates']} (sẽ dùng ảnh fallback)")
    if checklist["missing_cutouts"]:
        print(f" -> [Thiếu Cutout] Chưa có ảnh tách nền cho: {checklist['missing_cutouts']}")

    ctx.state_mgr.save_state(sb)
    return True

def run_stage_props(ctx: PipelineContext) -> bool:
    """Xuất hợp đồng render_props.json & đồng bộ tài sản sang Remotion."""
    print(f"\n[Stage: props] 📦 Xuất hợp đồng render_props.json & đồng bộ tài sản sang Remotion...")
    sb = ctx.state_mgr.load_state()
    if not sb:
        print("[Lỗi] Không tìm thấy storyboard. Vui lòng chạy stage script và audio trước.")
        return False

    words_map = {}
    for shot in sb.shots:
        if shot.words_file and os.path.exists(shot.words_file):
            with open(shot.words_file, "r", encoding="utf-8") as wf:
                words_map[shot.shot_id] = json.load(wf)

    exporter = RemotionPropsExporter()
    try:
        exporter.export(
            storyboard=sb,
            settings=ctx.settings,
            output_dir=ctx.chapter_dir,
            words_map=words_map,
        )
        print(f" -> Đã xuất render_props.json thành công tại: {ctx.chapter_dir / 'render_props.json'}")
        return True
    except Exception as e:
        print(f"[Lỗi] Khi xuất render_props: {e}")
        return False

def run_stage_stills(ctx: PipelineContext) -> bool:
    """Render contact sheet ảnh still cho chương truyện."""
    print(f"\n[Stage: stills] 📸 Render contact sheet ảnh still cho chương: '{ctx.chapter_id}'...")
    props_path = ctx.chapter_dir / "render_props.json"
    if not props_path.exists():
        print(f"[Lỗi] Chưa có render_props.json. Vui lòng chạy stage props trước.")
        return False

    stills_gen = StillsGenerator()
    out_stills_dir = ctx.chapter_dir / "stills"
    paths = stills_gen.render_scene_stills(props_path, out_stills_dir)
    print(f" -> Đã render {len(paths)} ảnh still tại: {out_stills_dir}")
    return True
