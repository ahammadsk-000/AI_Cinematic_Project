# Style Presets (mirror of `templates.py`)

Each style biases SDXL toward an aesthetic. Edit `STYLE_POSITIVE` / `STYLE_NEGATIVE`
in `templates.py` to change behavior — these are documentation copies.

## Cinematic Realistic
- **Positive:** cinematic film still, 35mm photograph, shallow depth of field, dramatic lighting, photorealistic, highly detailed, professional color grading, anamorphic
- **Negative:** cartoon, anime, illustration, low quality, blurry, deformed, extra limbs, text, watermark, oversaturated

## Anime
- **Positive:** anime key visual, cel shaded, vibrant, studio-quality 2D animation, detailed line art, expressive, by Makoto Shinkai
- **Negative:** photorealistic, 3d render, low quality, blurry, extra fingers, text, watermark

## Cyberpunk
- **Positive:** cyberpunk, neon-lit, rain-soaked streets, holographic signage, blade-runner aesthetic, volumetric fog, cinematic, ultra detailed
- **Negative:** daylight, rural, low quality, blurry, deformed, text, watermark, washed out

## Fantasy
- **Positive:** epic fantasy concept art, painterly, magical atmosphere, sweeping vista, dramatic god rays, intricate detail, trending on artstation
- **Negative:** modern, urban, low quality, blurry, deformed, text, watermark

## Portrait
- **Positive:** cinematic portrait, soft key light, 85mm lens, bokeh, skin texture detail, professional headshot lighting, photorealistic
- **Negative:** deformed face, asymmetric eyes, extra fingers, low quality, blurry, text, watermark, distorted features

**Shared quality baseline (appended to every negative):**
`worst quality, low quality, jpeg artifacts, signature, username, error, cropped`
