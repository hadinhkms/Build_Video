import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


class StillsGenerator:
    """Tạo ảnh tĩnh (contact sheet / still review) cho từng phân cảnh từ render_props.json."""

    def __init__(self, remotion_dir: Optional[Path] = None):
        self.root = Path(__file__).resolve().parent.parent.parent
        self.remotion_dir = remotion_dir or (self.root / "remotion")

    def render_scene_stills(
        self,
        props_path: Path,
        output_stills_dir: Path,
        composition_id: str = "StoryComposition",
    ) -> List[Path]:
        output_stills_dir.mkdir(parents=True, exist_ok=True)
        if not props_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file render_props: {props_path}")

        with open(props_path, "r", encoding="utf-8") as f:
            props_data = json.load(f)

        scenes = props_data.get("scenes", [])
        rendered_paths: List[Path] = []

        current_frame = 0
        npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"

        props_rel = os.path.relpath(props_path, self.remotion_dir).replace("\\", "/")

        for idx, scene in enumerate(scenes):
            scene_id = scene.get("id", f"scene_{idx}")
            dur_frames = int(scene.get("durationInFrames", 60))
            mid_frame = current_frame + (dur_frames // 2)

            out_png = output_stills_dir / f"{scene_id}_f{mid_frame}.png"
            out_png_rel = os.path.relpath(out_png, self.remotion_dir).replace("\\", "/")

            cmd = [
                npx_cmd,
                "remotion",
                "still",
                "src/index.ts",
                composition_id,
                out_png_rel,
                f"--frame={mid_frame}",
                f"--props={props_rel}",
            ]

            print(f" -> Rendering still cảnh '{scene_id}' tại frame {mid_frame}...")
            res = subprocess.run(cmd, cwd=str(self.remotion_dir), shell=True)
            if res.returncode == 0 and out_png.exists():
                rendered_paths.append(out_png)
            else:
                print(f"[Cảnh báo] Không render được still cho cảnh '{scene_id}' (frame {mid_frame})")

            current_frame += dur_frames

        return rendered_paths
