from enum import Enum
from typing import Dict, List, Optional
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
    narrative_act: NarrativeAct = NarrativeAct.SETUP
    voiceover: str
    shot_type: str = "medium shot"
    action: str
    character_id: str = "nhan_vat_chinh"
    environment_id: str = "phong_khach_dem_mua"
    camera_motion: str = "zoom_in"
    sfx_cue: Optional[str] = ""
    prompt: str = ""
    duration: float = 5.0
    audio_file: Optional[str] = None
    words_file: Optional[str] = None  # [{text, start, end}] từ Edge-TTS WordBoundary
    image_file: Optional[str] = None
    video_clip_file: Optional[str] = None
    status: ShotStatus = ShotStatus.PENDING

class Storyboard(BaseModel):
    chapter_id: str = "chapter_01"
    title: str = "Chương truyện điện ảnh"
    shots: List[Shot] = Field(default_factory=list)
    total_duration: float = 0.0
