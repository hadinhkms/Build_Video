import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.core.scratch_manager import ScratchManager


class StillsGenerator:
    """Tạo ảnh tĩnh (contact sheet / still review) cho từng phân cảnh từ render_props.json.

    Sử dụng 1 phiên `scripts/render_stills.ts` duy nhất (dùng chung NVMe bundle-cache và
    1 phiên Chromium qua `openBrowser()` + `puppeteerInstance`) thay cho vòng lặp N lần `npx remotion still`.
    """

    def __init__(
        self,
        remotion_dir: Optional[Path] = None,
        project_root: Optional[Path] = None,
    ):
        self.root = Path(project_root) if project_root else Path(__file__).resolve().parent.parent.parent
        self.remotion_dir = Path(remotion_dir) if remotion_dir else (self.root / "remotion")
        self.last_summary: Dict[str, Any] = {}

    def _resolve_defaults(
        self,
        scratch_dir: Optional[Union[Path, str]],
        gl: Optional[str],
    ) -> tuple[Optional[Path], str]:
        resolved_scratch = Path(scratch_dir).resolve() if scratch_dir is not None else None
        resolved_gl = gl

        render_cfg: Dict[str, Any] = {}
        settings_path = self.root / "config" / "settings.json"
        if settings_path.exists():
            try:
                render_cfg = json.loads(settings_path.read_text(encoding="utf-8")).get("render", {})
            except Exception:
                render_cfg = {}

        if not resolved_gl:
            resolved_gl = str(render_cfg.get("gl") or "angle")

        if resolved_scratch is None:
            try:
                mgr = ScratchManager(
                    project_root=self.root,
                    scratch_dir_setting=str(render_cfg.get("scratch_dir", "auto")),
                )
                resolved_scratch = mgr.scratch_root
            except Exception:
                resolved_scratch = None

        return resolved_scratch, resolved_gl

    def build_command(
        self,
        props_path: Path,
        output_stills_dir: Path,
        composition_id: str = "StoryComposition",
        scratch_dir: Optional[Union[Path, str]] = None,
        chapter_id: Optional[str] = None,
        gl: str = "angle",
        concurrency: int = 6,
        bundle_cache: bool = True,
    ) -> List[str]:
        npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"
        cmd = [
            npx_cmd,
            "tsx",
            "scripts/render_stills.ts",
            "--props",
            str(Path(props_path).resolve()),
            "--all-scenes",
            "--out-dir",
            str(Path(output_stills_dir).resolve()),
            "--composition",
            str(composition_id),
            "--concurrency",
            str(max(1, int(concurrency))),
            "--gl",
            str(gl),
        ]
        if scratch_dir is not None:
            cmd.extend(["--scratch-dir", str(Path(scratch_dir).resolve())])
        if chapter_id:
            cmd.extend(["--chapter-id", str(chapter_id)])
        if not bundle_cache:
            cmd.append("--no-bundle-cache")
        return cmd

    def render_scene_stills(
        self,
        props_path: Path,
        output_stills_dir: Path,
        composition_id: str = "StoryComposition",
        scratch_dir: Optional[Union[Path, str]] = None,
        chapter_id: Optional[str] = None,
        gl: Optional[str] = None,
        concurrency: int = 6,
        bundle_cache: bool = True,
    ) -> List[Path]:
        props_path = Path(props_path)
        output_stills_dir = Path(output_stills_dir)
        output_stills_dir.mkdir(parents=True, exist_ok=True)
        self.last_summary = {}

        if not props_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file render_props: {props_path}")

        with open(props_path, "r", encoding="utf-8") as f:
            props_data = json.load(f)

        scenes = props_data.get("scenes", [])
        if not scenes:
            return []

        resolved_chapter_id = chapter_id or props_data.get("chapterId")
        resolved_scratch, resolved_gl = self._resolve_defaults(scratch_dir, gl)

        # Tính trước danh sách tệp kỳ vọng theo đúng thứ tự scene
        expected_paths: List[Path] = []
        current_frame = 0
        for idx, scene in enumerate(scenes):
            scene_id = scene.get("id", f"scene_{idx}")
            dur_frames = max(1, int(scene.get("durationInFrames", 60)))
            mid_frame = current_frame + (dur_frames // 2)
            expected_paths.append(output_stills_dir / f"{scene_id}_f{mid_frame}.png")
            current_frame += dur_frames

        cmd = self.build_command(
            props_path=props_path,
            output_stills_dir=output_stills_dir,
            composition_id=composition_id,
            scratch_dir=resolved_scratch,
            chapter_id=resolved_chapter_id,
            gl=resolved_gl,
            concurrency=concurrency,
            bundle_cache=bundle_cache,
        )

        print(
            f" -> Batch render {len(scenes)} ảnh still qua 1 phiên Chromium "
            f"(concurrency={concurrency}, gl={resolved_gl})..."
        )
        res = subprocess.run(
            cmd,
            cwd=str(self.remotion_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        for line in (res.stdout or "").splitlines():
            stripped = line.strip()
            if stripped.startswith("STILL_SUMMARY"):
                for token in stripped.split()[1:]:
                    if "=" in token:
                        k, v = token.split("=", 1)
                        self.last_summary[k] = v
                print(f" -> {stripped}")
            elif stripped.startswith("BUNDLE_CACHE"):
                print(f" -> {stripped}")

        if res.returncode != 0:
            err_tail = (res.stderr or res.stdout or "").strip()[-400:]
            print(f"[Cảnh báo] render_stills.ts trả mã lỗi {res.returncode}: {err_tail}")

        rendered_paths = [p for p in expected_paths if p.exists()]
        return rendered_paths
