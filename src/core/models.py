"""Mô hình dữ liệu lõi của CineStory Engine.

Bao gồm:
1. Hợp đồng dữ liệu render_props (Pydantic ↔ Zod strict contract) trong `src.core.contracts`.
2. Các thực thể Storyboard, Shot, CameraMotion, Nhân vật & Bối cảnh trong `src.core.entities`.
"""

from src.core.contracts import (
    Ambience,
    Bgm,
    Caption,
    CharacterAnchor,
    ClipFit,
    ContractModel,
    Effects,
    FaceRig,
    Grade,
    Rect,
    RenderProps,
    Scene,
    SceneAudio,
    Sec,
    Sfx,
    Style,
    Visual,
    Word,
)
from src.core.entities import (
    CameraMotion,
    CharacterDNA,
    EnvironmentAnchor,
    NarrativeAct,
    Shot,
    ShotKind,
    ShotStatus,
    ShotType,
    SpatialAnchors,
    Storyboard,
)

__all__ = [
    # Contracts
    "Sec",
    "ContractModel",
    "Word",
    "Caption",
    "Sfx",
    "Rect",
    "CharacterAnchor",
    "Grade",
    "Effects",
    "Style",
    "ClipFit",
    "FaceRig",
    "Visual",
    "SceneAudio",
    "Scene",
    "Ambience",
    "Bgm",
    "RenderProps",
    # Entities
    "NarrativeAct",
    "ShotStatus",
    "ShotType",
    "ShotKind",
    "CameraMotion",
    "CharacterDNA",
    "SpatialAnchors",
    "EnvironmentAnchor",
    "Shot",
    "Storyboard",
]
