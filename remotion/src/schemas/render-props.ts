import { z } from "zod";

const Sec = z.number().nonnegative();
const Frac = z.number().min(0).max(1);

export const RectSchema = z.object({
  x: Frac,
  y: Frac,
  w: Frac,
  h: Frac,
}).strict();

export const CharacterAnchorSchema = z.object({
  x: Frac,
  y: z.number().min(0).max(1.2),
  height: Frac,
}).strict();

export const GradeSchema = z.object({
  cssFilter: z.string(),
  overlayGradient: z.string().nullable(),
  overlayBlend: z.enum(["soft-light", "overlay", "multiply", "screen"]),
  contactShadowOpacity: Frac,
}).strict();

export const EffectsSchema = z.object({
  rain: z.enum(["window", "full", "off"]),
  rainRegion: RectSchema.nullable(),
  flicker: z.boolean(),
}).strict().superRefine((data, ctx) => {
  if (data.rain === "window" && data.rainRegion === null) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "rainRegion is required when rain is 'window'",
      path: ["rainRegion"],
    });
  }
  if (data.rain !== "window" && data.rainRegion !== null) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "rainRegion must be null when rain is not 'window'",
      path: ["rainRegion"],
    });
  }
});

export const StyleSchema = z.object({
  subtitles: z.boolean(),
  letterboxRatio: z.number().positive().nullable(),
  grain: z.boolean(),
}).strict();

export const WordSchema = z.object({
  text: z.string(),   // từ theo VĂN BẢN GỐC (đã căn ở Phase 1)
  start: Sec,
  end: Sec,
}).strict();

export const CaptionSchema = z.object({
  text: z.string(),                // cụm 3–6 từ, văn bản gốc
  start: Sec,
  end: Sec,
  highlight: z.array(z.string()),  // cụm từ khóa cần tô màu (có thể nhiều từ); không có thì []
}).strict();

export const SfxSchema = z.object({
  src: z.string(),
  startSec: Sec,                    // tính từ đầu cảnh, Python kẹp về ≥ 0
  volume: z.number().min(0).max(1), // tuyến tính, đã đổi từ dB ở Python
  durationSec: Sec.nullable(),      // null = phát hết file
  fadeInSec: Sec,                   // không fade thì ghi 0
  fadeOutSec: Sec,
}).strict();

export const ClipFitSchema = z.object({
  playbackRate: z.number().positive().max(1),
  freezeAtFrame: z.number().int().nonnegative().nullable(),
  loop: z.boolean(),
}).strict();

export const FaceRigSchema = z.object({
  eyesPatchSrc: z.string().nullable(),
  mouthPatchSrc: z.string().nullable(),
  eyes: RectSchema.nullable(),
  mouth: RectSchema.nullable(),
}).strict();

export const VisualSchema = z.object({
  mode: z.enum(["layered", "full_image", "clip"]),
  imageSrc: z.string().nullable(),
  backgroundSrc: z.string().nullable(),
  characterSrc: z.string().nullable(),
  clipSrc: z.string().nullable(),
  characterAnchor: CharacterAnchorSchema.nullable(),
  cropRect: RectSchema.nullable(),
  clipDurationSec: Sec.nullable(),
  clipFit: ClipFitSchema.nullable(),
  faceRig: FaceRigSchema.nullable(),
}).strict().superRefine((data, ctx) => {
  if (data.mode === "clip" && data.clipFit === null) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "clipFit is required when mode is 'clip'",
      path: ["clipFit"],
    });
  }
  if (data.mode !== "clip" && data.clipFit !== null) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "clipFit must be null when mode is not 'clip'",
      path: ["clipFit"],
    });
  }
});

export const SceneAudioSchema = z.object({
  src: z.string(),
  startInFileSec: Sec,   // 0 với cảnh thường; > 0 với cảnh con thứ 2 trở đi
  durationSec: Sec,      // độ dài đoạn audio phát trong cảnh này
}).strict();

export const SceneSchema = z.object({
  id: z.string(),
  kind: z.enum(["story", "title_card", "end_screen"]),
  act: z.enum(["HOOK", "SETUP", "RISING", "CLIMAX", "CLIFFHANGER"]),
  rawText: z.string(),                       // hiển thị (phụ đề)
  voiceText: z.string(),                     // đưa vào TTS (Phase 1 chuẩn hóa)
  speaker: z.string(),                       // "narrator" hoặc key trong characters.json
  isDialogue: z.boolean(),
  onScreenCharacterId: z.string().nullable(),
  environmentId: z.string(),
  shotType: z.enum(["wide", "medium", "closeup", "extreme_closeup", "over_shoulder"]),
  cameraMotion: z.enum(["zoom_in", "rapid_zoom_in", "zoom_out", "pan_left", "pan_right", "static"]),
  durationInFrames: z.number().int().positive(), // BẮT BUỘC, không có giá trị mặc định
  audio: SceneAudioSchema.nullable(),
  words: z.array(WordSchema),
  captions: z.array(CaptionSchema),
  sfx: z.array(SfxSchema),
  visual: VisualSchema,
  effects: EffectsSchema,
  grade: GradeSchema.nullable(),
  mouthEnvelope: z.array(z.number().min(0).max(1)).nullable(),
}).strict().superRefine((data, ctx) => {
  if (data.mouthEnvelope !== null && data.mouthEnvelope.length !== data.durationInFrames) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: `mouthEnvelope length (${data.mouthEnvelope.length}) must match durationInFrames (${data.durationInFrames})`,
      path: ["mouthEnvelope"],
    });
  }
});

export const AmbienceSchema = z.object({
  src: z.string(),
  startSec: Sec,   // tuyệt đối
  endSec: Sec,
  volume: z.number().min(0).max(1),
  fadeSec: Sec,
}).strict();

export const BgmSchema = z.object({
  src: z.string(),
  volume: z.number().min(0).max(1),        // mức nền khi không có giọng
  duckedVolume: z.number().min(0).max(1),  // mức khi có giọng
  duckIntervals: z.array(z.tuple([Sec, Sec])), // giây tuyệt đối
  cutAtSec: Sec.nullable(),                // tắt nhạc ở CLIFFHANGER (Phase 1)
}).strict();

export const RenderPropsSchema = z.object({
  schemaVersion: z.literal(1),
  chapterId: z.string(),
  title: z.string(),
  fps: z.number().int().positive(),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
  scenes: z.array(SceneSchema).min(1),
  ambience: z.array(AmbienceSchema),
  bgm: BgmSchema.nullable(),
  style: StyleSchema,
}).strict();

export type Rect = z.infer<typeof RectSchema>;
export type CharacterAnchor = z.infer<typeof CharacterAnchorSchema>;
export type Grade = z.infer<typeof GradeSchema>;
export type Effects = z.infer<typeof EffectsSchema>;
export type Style = z.infer<typeof StyleSchema>;
export type Word = z.infer<typeof WordSchema>;
export type Caption = z.infer<typeof CaptionSchema>;
export type Sfx = z.infer<typeof SfxSchema>;
export type ClipFit = z.infer<typeof ClipFitSchema>;
export type FaceRig = z.infer<typeof FaceRigSchema>;
export type Visual = z.infer<typeof VisualSchema>;
export type SceneAudio = z.infer<typeof SceneAudioSchema>;
export type Scene = z.infer<typeof SceneSchema>;
export type Ambience = z.infer<typeof AmbienceSchema>;
export type Bgm = z.infer<typeof BgmSchema>;
export type RenderProps = z.infer<typeof RenderPropsSchema>;
