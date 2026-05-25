"""Cinematic prompt-engineering templates and style vocabulary.

This is the single source of truth for how the platform "thinks" cinematically:
  * the LLM system prompt that turns a script into structured scenes,
  * per-style positive suffixes / negative prompts that bias SDXL,
  * camera + lighting vocabularies the prompt enhancer can draw on.

Human-readable copies live under repo-root prompts/ for non-developers to tweak;
this module is the importable canonical version.
"""

from __future__ import annotations

from ai_engine.interfaces import StyleMode

# --------------------------------------------------------------------------- #
# LLM system prompt: script -> structured scenes
# --------------------------------------------------------------------------- #
SCENE_SYSTEM_PROMPT = """You are a cinematic director and storyboard artist. Given a short \
script or story idea, break it into a sequence of distinct visual SCENES for an AI-generated film.

Return STRICT JSON only, no prose, in exactly this shape:
{{
  "character": "ONE fixed, detailed physical description of the main recurring subject \
(age, ethnicity, face shape, eyes, hair, clothing, distinguishing features). This exact \
description must apply to EVERY scene so the same person is rendered each time.",
  "scenes": [
    {{
      "summary": "one sentence describing what happens in the shot",
      "environment": "the setting, location, time of day, weather",
      "camera": "shot type + camera movement (e.g. 'low-angle slow dolly-in', 'wide establishing', 'close-up')",
      "lighting": "lighting style (e.g. 'neon rim light with volumetric fog', 'golden-hour backlight')",
      "emotion": "the emotional tone (e.g. 'lonely and tense')",
      "motion": "what moves in the shot, for animation (e.g. 'rain falls, character walks forward')",
      "music_mood": "background music mood (e.g. 'melancholic synthwave')",
      "sound_effects": ["list", "of", "ambient sfx"],
      "narration": "a short voice-over line for this scene, or empty string",
      "duration_sec": 4.0
    }}
  ]
}}

Rules:
- "character" is mandatory: derive it from the script's main subject and keep it
  IDENTICAL for the whole video (this is how we keep the same face across scenes).
- Produce between 3 and {max_scenes} scenes. Keep visual continuity between them.
- The visual style is "{style}". Bias every scene toward that aesthetic.
- Keep each field concise (a phrase, not a paragraph).
- duration_sec should be 3-6 seconds per scene.
- NARRATION: if the script already contains explicit voice-over / narration lines
  (e.g. quoted text, or lines tagged with timestamps like "(0-3s)"), copy them
  VERBATIM into the matching scene's "narration" field, preserving the ORIGINAL
  language and wording exactly. Only invent narration when the script provides none.
- Output ONLY the JSON object."""


# --------------------------------------------------------------------------- #
# Per-style SDXL biasing
# --------------------------------------------------------------------------- #
STYLE_POSITIVE: dict[StyleMode, str] = {
    StyleMode.CINEMATIC_REALISTIC: "cinematic film still, 35mm photograph, shallow depth of field, "
    "dramatic lighting, photorealistic, highly detailed, professional color grading, anamorphic",
    StyleMode.ANIME: "anime key visual, cel shaded, vibrant, studio-quality 2D animation, "
    "detailed line art, expressive, by Makoto Shinkai",
    StyleMode.CYBERPUNK: "cyberpunk, neon-lit, rain-soaked streets, holographic signage, "
    "blade-runner aesthetic, volumetric fog, cinematic, ultra detailed",
    StyleMode.FANTASY: "epic fantasy concept art, painterly, magical atmosphere, sweeping vista, "
    "dramatic god rays, intricate detail, trending on artstation",
    StyleMode.PORTRAIT: "cinematic portrait, soft key light, 85mm lens, bokeh, skin texture detail, "
    "professional headshot lighting, photorealistic",
}

STYLE_NEGATIVE: dict[StyleMode, str] = {
    StyleMode.CINEMATIC_REALISTIC: "cartoon, anime, illustration, low quality, blurry, deformed, "
    "extra limbs, text, watermark, oversaturated",
    StyleMode.ANIME: "photorealistic, 3d render, low quality, blurry, extra fingers, text, watermark",
    StyleMode.CYBERPUNK: "daylight, rural, low quality, blurry, deformed, text, watermark, washed out",
    StyleMode.FANTASY: "modern, urban, low quality, blurry, deformed, text, watermark",
    StyleMode.PORTRAIT: "deformed face, asymmetric eyes, extra fingers, low quality, blurry, "
    "text, watermark, distorted features",
}

# A baseline negative applied to every style.
BASE_NEGATIVE = "worst quality, low quality, jpeg artifacts, signature, username, error, cropped"

CAMERA_VOCAB = [
    "wide establishing shot", "low-angle dolly-in", "slow push-in close-up", "tracking shot",
    "crane shot", "over-the-shoulder", "dutch angle", "aerial drone shot",
]

LIGHTING_VOCAB = [
    "neon rim light with volumetric fog", "golden-hour backlight", "moody chiaroscuro",
    "soft diffused key light", "harsh top light", "bioluminescent ambient glow",
]


def style_suffix(style: StyleMode) -> str:
    return STYLE_POSITIVE.get(style, STYLE_POSITIVE[StyleMode.CINEMATIC_REALISTIC])


def style_negative(style: StyleMode) -> str:
    specific = STYLE_NEGATIVE.get(style, "")
    return f"{specific}, {BASE_NEGATIVE}" if specific else BASE_NEGATIVE
