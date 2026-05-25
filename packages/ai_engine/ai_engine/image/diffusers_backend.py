"""DiffusersImageBackend — secondary in-process SDXL adapter.

Used when ComfyUI isn't available (e.g. a bare Kaggle kernel) or for debugging.
All heavy imports (torch, diffusers) are lazy and confined to load(), so importing
this module on a CPU box never fails — the registry can reference it freely.

Implements the low-VRAM levers from docs/ARCHITECTURE.md §6: fp16, sequential CPU
offload, VAE tiling/slicing, all gated by EngineConfig.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Optional

from ai_engine.config import EngineConfig
from ai_engine.interfaces import Artifact, Character, GenerationConfig, ImageBackend, Scene
from ai_engine.utils.logging import get_logger
from ai_engine.utils.vram import VRAMError, empty_cache, is_oom

log = get_logger("diffusers")

_DEFAULT_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"


class DiffusersImageBackend(ImageBackend):
    def __init__(self, cfg: EngineConfig, model_id: str = _DEFAULT_MODEL) -> None:
        self.cfg = cfg
        self.model_id = model_id
        self.output_dir = Path.cwd()
        self._pipe: Any = None

    @classmethod
    def from_config(cls, cfg: EngineConfig) -> "DiffusersImageBackend":
        return cls(cfg)

    @property
    def is_loaded(self) -> bool:
        return self._pipe is not None

    def load(self) -> None:
        if self._pipe is not None:
            return
        import torch  # noqa: PLC0415
        from diffusers import StableDiffusionXLPipeline  # noqa: PLC0415

        dtype = torch.float16 if self.cfg.use_fp16 else torch.float32
        log.info("loading SDXL via diffusers (%s, fp16=%s)", self.model_id, self.cfg.use_fp16)
        pipe = StableDiffusionXLPipeline.from_pretrained(
            self.model_id, torch_dtype=dtype, variant="fp16" if self.cfg.use_fp16 else None, use_safetensors=True,
            cache_dir=str(self.cfg.model_cache),
        )
        if self.cfg.enable_cpu_offload:
            pipe.enable_sequential_cpu_offload()       # biggest VRAM saver on T4
        else:
            pipe.to("cuda")
        if self.cfg.enable_vae_tiling:
            pipe.enable_vae_tiling()
            pipe.enable_vae_slicing()
        pipe.enable_attention_slicing()
        self._pipe = pipe

    def unload(self) -> None:
        if self._pipe is not None:
            del self._pipe
            self._pipe = None
            empty_cache()
            log.info("diffusers pipeline unloaded")

    def generate_image(
        self,
        scene: Scene,
        cfg: GenerationConfig,
        *,
        characters: Optional[list[Character]] = None,
        control_image: Optional[Path] = None,
    ) -> Artifact:
        if self._pipe is None:
            self.load()
        import torch  # noqa: PLC0415

        seed = cfg.seed if cfg.seed is not None else random.randint(0, 2**32 - 1)
        generator = torch.Generator(device="cpu").manual_seed(seed)
        try:
            result = self._pipe(
                prompt=scene.prompt,
                negative_prompt=scene.negative_prompt,
                width=cfg.width,
                height=cfg.height,
                num_inference_steps=cfg.steps,
                guidance_scale=cfg.cfg_scale,
                generator=generator,
            )
        except RuntimeError as exc:
            if is_oom(exc):
                empty_cache()
                raise VRAMError(str(exc)) from exc  # orchestrator retries smaller
            raise

        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.output_dir / f"cineforge_s{scene.index}_{seed}.png"
        result.images[0].save(out_path)
        log.info("scene %d image saved -> %s", scene.index, out_path.name)
        return Artifact(path=out_path, kind="image", scene_index=scene.index, meta={"seed": seed})
