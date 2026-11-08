from typing import Any, Dict, List, Literal, Optional, Tuple, Union
from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, field_validator, model_validator
from pydantic.alias_generators import to_camel

# ==============================================================================
# HỢP ĐỒNG DỮ LIỆU RENDER_PROPS (PYDANTIC ↔ ZOD STRICT CONTRACT)
# ==============================================================================

Sec = NonNegativeFloat

class ContractModel(BaseModel):
    # strict=True: không tự ép kiểu ("1.5" -> 1.5, "true" -> True) giống Zod
    # extra="forbid": cấm các trường lạ không được khai báo
    # alias_generator=to_camel: sinh key camelCase cho JSON
    # populate_by_name=True: cho phép khởi tạo bằng snake_case trong Python
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        strict=True,
    )

class Word(ContractModel):
    text: str
    start: Sec
    end: Sec

class Caption(ContractModel):
    text: str
    start: Sec
    end: Sec
    highlight: List[str]

class Sfx(ContractModel):
    src: str
    start_sec: Sec
    volume: float = Field(ge=0.0, le=1.0)
    duration_sec: Optional[Sec]
    fade_in_sec: Sec
    fade_out_sec: Sec

class Rect(ContractModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(ge=0.0, le=1.0)
    h: float = Field(ge=0.0, le=1.0)

class CharacterAnchor(ContractModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.2)
    height: float = Field(ge=0.0, le=1.0)

class Grade(ContractModel):
    css_filter: str
    overlay_gradient: Optional[str]
    overlay_blend: Literal["soft-light", "overlay", "multiply", "screen"]
    contact_shadow_opacity: float = Field(ge=0.0, le=1.0)

class Effects(ContractModel):
    rain: Literal["window", "full", "off"]
    rain_region: Optional[Rect]
    flicker: bool

    @model_validator(mode="after")
    def validate_rain_region(self) -> "Effects":
        if self.rain == "window" and self.rain_region is None:
            raise ValueError("rainRegion bắt buộc có khi rain='window'")
        if self.rain != "window" and self.rain_region is not None:
            raise ValueError("rainRegion phải là null khi rain!='window'")
        return self

class Style(ContractModel):
    subtitles: bool
    letterbox_ratio: Optional[float] = Field(gt=0)
    grain: bool

class ClipFit(ContractModel):
    playback_rate: float = Field(gt=0, le=1.0)
    freeze_at_frame: Optional[int] = Field(None, ge=0)
    loop: bool

class FaceRig(ContractModel):
    eyes_patch_src: Optional[str] = None
    mouth_patch_src: Optional[str] = None
    eyes: Optional[Rect] = None
    mouth: Optional[Rect] = None

class Visual(ContractModel):
    mode: Literal["layered", "full_image", "clip"]
    image_src: Optional[str]
    background_src: Optional[str]
    character_src: Optional[str]
    clip_src: Optional[str]
    character_anchor: Optional[CharacterAnchor]
    crop_rect: Optional[Rect]
    clip_duration_sec: Optional[Sec] = None
    clip_fit: Optional[ClipFit] = None
    face_rig: Optional[FaceRig] = None

    @model_validator(mode="after")
    def validate_clip_fit(self) -> "Visual":
        if self.mode == "clip" and self.clip_fit is None:
            raise ValueError("clipFit must not be null when mode is 'clip'")
        if self.mode != "clip" and self.clip_fit is not None:
            raise ValueError("clipFit must be null when mode is not 'clip'")
        return self

class SceneAudio(ContractModel):
    src: str
    start_in_file_sec: Sec
    duration_sec: Sec

class Scene(ContractModel):
    id: str
    kind: Literal["story", "title_card", "end_screen"]
    act: Literal["HOOK", "SETUP", "RISING", "CLIMAX", "CLIFFHANGER"]
    raw_text: str
    voice_text: str
    speaker: str
    is_dialogue: bool
    on_screen_character_id: Optional[str]
    environment_id: str
    shot_type: Literal["wide", "medium", "closeup", "extreme_closeup", "over_shoulder"]
    camera_motion: Literal["zoom_in", "rapid_zoom_in", "zoom_out", "pan_left", "pan_right", "static"]
    duration_in_frames: int = Field(gt=0)
    audio: Optional[SceneAudio]
    words: List[Word]
    captions: List[Caption]
    sfx: List[Sfx]
    visual: Visual
    effects: Effects
    grade: Optional[Grade]
    mouth_envelope: Optional[List[float]] = Field(None)

    @model_validator(mode="after")
    def validate_mouth_envelope(self) -> "Scene":
        if self.mouth_envelope is not None:
            if len(self.mouth_envelope) != self.duration_in_frames:
                raise ValueError(
                    f"mouth_envelope length ({len(self.mouth_envelope)}) must equal duration_in_frames ({self.duration_in_frames})"
                )
            for val in self.mouth_envelope:
                if not (0.0 <= val <= 1.0):
                    raise ValueError(f"mouth_envelope values must be in [0, 1], got {val}")
        return self

class Ambience(ContractModel):
    src: str
    start_sec: Sec
    end_sec: Sec
    volume: float = Field(ge=0.0, le=1.0)
    fade_sec: Sec

class Bgm(ContractModel):
    src: str
    volume: float = Field(ge=0.0, le=1.0)
    ducked_volume: float = Field(ge=0.0, le=1.0)
    duck_intervals: List[Tuple[Sec, Sec]]
    cut_at_sec: Optional[Sec]

    @field_validator("duck_intervals", mode="before")
    @classmethod
    def convert_intervals_to_tuples(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [tuple(item) if isinstance(item, list) else item for item in v]
        return v

class RenderProps(ContractModel):
    schema_version: Literal[1]
    chapter_id: str
    title: str
    fps: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    scenes: List[Scene] = Field(min_length=1)
    ambience: List[Ambience]
    bgm: Optional[Bgm]
    style: Style
