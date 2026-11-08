from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class NarrativeAct(str, Enum):
    HOOK = "HOOK"
    SETUP = "SETUP"
    RISING = "RISING"
    CLIMAX = "CLIMAX"
    CLIFFHANGER = "CLIFFHANGER"


class ShotStatus(str, Enum):
    PENDING = "PENDING"
    AUDIO_READY = "AUDIO_READY"
    VISUAL_READY = "VISUAL_READY"
    ACTING_READY = "ACTING_READY"
    COMPOSITED = "COMPOSITED"
    FAILED = "FAILED"


class ShotType(str, Enum):
    WIDE = "wide"
    MEDIUM = "medium"
    CLOSEUP = "closeup"
    EXTREME_CLOSEUP = "extreme_closeup"
    OVER_SHOULDER = "over_shoulder"


class ShotKind(str, Enum):
    STORY = "story"
    TITLE_CARD = "title_card"
    END_SCREEN = "end_screen"


class CameraMotion(str, Enum):
    ZOOM_IN = "zoom_in"
    RAPID_ZOOM_IN = "rapid_zoom_in"
    ZOOM_OUT = "zoom_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    STATIC = "static"


class CharacterDNA(BaseModel):
    id: str
    name: str
    role: str = "Nhân vật chính"
    age: int = 28
    gender: str = "Nam"
    face_reference_image: str = "assets/characters/main_char_face.jpg"
    dna_prompt: str
    fixed_wardrobe: str
    forbidden_traits: Optional[str] = "no anime, no plastic skin, no 3d cartoon"


class SpatialAnchors(BaseModel):
    left: str = ""
    center: str = ""
    right: str = ""
    background: str = ""


class EnvironmentAnchor(BaseModel):
    id: str
    name: str
    spatial_anchors: SpatialAnchors
    lighting: str
    weather: str
    camera_profile: str


class Shot(BaseModel):
    shot_id: str
    kind: ShotKind = ShotKind.STORY
    narrative_act: NarrativeAct = NarrativeAct.SETUP
    voiceover: str = ""
    voice_text: str = ""
    raw_text: str = ""
    speaker: str = "narrator"
    is_dialogue: bool = False
    on_screen_character_id: Optional[str] = None
    character_id: str = "nhan_vat_chinh"
    environment_id: str = "phong_khach_dem_mua"
    shot_type: str = "medium shot"
    shot_prompt: str = ""
    action: str = ""
    camera_motion: str = "zoom_in"
    sfx_cue: Optional[str] = ""
    prompt: str = ""
    duration: float = 5.0
    duration_frames: int = 120
    audio_start_in_file_sec: float = 0.0
    parent_id: Optional[str] = None
    audio_file: Optional[str] = None
    words_file: Optional[str] = None
    image_file: Optional[str] = None
    video_clip_file: Optional[str] = None
    status: ShotStatus = ShotStatus.PENDING


class Storyboard(BaseModel):
    chapter_id: str = "chapter_01"
    title: str = "Chương truyện điện ảnh"
    shots: List[Shot] = Field(default_factory=list)
    total_duration: float = 0.0
