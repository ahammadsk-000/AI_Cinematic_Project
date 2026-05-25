# Prompt Engineering Templates

The **canonical, importable** templates live in
[`packages/ai_engine/ai_engine/scene/templates.py`](../packages/ai_engine/ai_engine/scene/templates.py).
This folder holds human-readable copies for non-developers to review and tweak;
keep them in sync if you edit one.

## Files

| File | Purpose |
|------|---------|
| `scene_system_prompt.md` | The system prompt that turns a script into structured scenes (used by `LLMSceneBackend`). |
| `style_presets.md` | Positive suffix + negative prompt per visual style (cinematic, anime, cyberpunk, fantasy, portrait). |

## How prompts flow through the pipeline

```
script ──(SCENE_SYSTEM_PROMPT)──► LLM ──► structured Scene[]
Scene + style ──(TemplatePromptEnhancer + style_presets)──► final SDXL prompt + negative
```

The enhancer concatenates, in SDXL-friendly order:
`summary, environment, camera, lighting, emotion, <style positive suffix>`
and pairs it with the style's negative prompt + a shared quality baseline.
