"""FalImageBackend — OPTIONAL high-quality stills via fal.ai Flux.

Self-contained, additive ImageBackend. Generates the per-scene still with a Flux
model on fal's servers (far cleaner cartoon/character images than base SDXL), so
it needs NO local GPU. Pairs naturally with the fal video backend (Flux still →
Kling motion). Enable with:

    CINEFORGE_IMAGE_BACKEND=fal-flux
    FAL_KEY=<your fal.ai key>
    FAL_IMAGE_MODEL=fal-ai/flux/dev        # optional (schnell=cheaper/faster, flux-pro=best)

Revert to free anytime: CINEFORGE_IMAGE_BACKEND=comfyui. Nothing else depends on
this file. Uses fal's async queue REST over httpx (no extra package).
"""

from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Optional

import httpx

from ai_engine.interfaces import Artifact, Character, GenerationConfig, ImageBackend, Scene
from ai_engine.utils.logging import get_logger
from ai_engine.utils.retry import retry

log = get_logger("fal_flux")

_DEFAULT_MODEL = "fal-ai/flux/dev"
_QUEUE_BASE = "https://queue.fal.run"


class FalImageBackend(ImageBackend):
    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self.api_key = api_key
        self.output_dir = Path.cwd()

    @classmethod
    def from_config(cls, cfg) -> "FalImageBackend":  # cfg: EngineConfig (duck-typed)
        key = os.getenv("FAL_KEY", "")
        if not key:
            raise ValueError("FAL_KEY is not set — required for CINEFORGE_IMAGE_BACKEND=fal-flux")
        return cls(model=os.getenv("FAL_IMAGE_MODEL", _DEFAULT_MODEL), api_key=key)

    # remote API → no local model/VRAM; lifecycle no-op
    @property
    def is_loaded(self) -> bool:
        return True

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def _headers(self) -> dict:
        return {"Authorization": f"Key {self.api_key}", "Content-Type": "application/json"}

    def build_input(self, scene: Scene, cfg: GenerationConfig) -> dict:
        """Pure: the Flux request payload (no network) — unit-testable.
        Flux is guidance-distilled (no negative prompt); uses a low guidance_scale."""
        seed = cfg.seed if cfg.seed is not None else random.randint(0, 2**31 - 1)
        return {
            "prompt": scene.prompt,
            "image_size": {"width": cfg.width, "height": cfg.height},
            "num_inference_steps": max(20, min(cfg.steps, 40)),
            "guidance_scale": 3.5,           # Flux-dev sweet spot
            "seed": seed,                    # fixed per job → character consistency
            "num_images": 1,
            "enable_safety_checker": False,
        }

    @retry(attempts=3, backoff=3.0, exceptions=(httpx.HTTPError,))
    def _submit(self, payload: dict) -> dict:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{_QUEUE_BASE}/{self.model}", json=payload, headers=self._headers())
            if resp.status_code >= 400:
                log.error("fal-flux %s on %s -> %s", resp.status_code, self.model, resp.text[:400])
            resp.raise_for_status()
            return resp.json()

    def _await_result(self, status_url: str, response_url: str, *, timeout_s: float = 300.0, poll_s: float = 2.0) -> dict:
        deadline = time.time() + timeout_s
        with httpx.Client(timeout=60.0) as client:
            while time.time() < deadline:
                st = client.get(status_url, headers=self._headers())
                st.raise_for_status()
                status = st.json().get("status")
                if status == "COMPLETED":
                    res = client.get(response_url, headers=self._headers())
                    res.raise_for_status()
                    return res.json()
                if status in ("FAILED", "ERROR"):
                    raise RuntimeError(f"fal-flux job failed: {st.json()}")
                time.sleep(poll_s)
        raise TimeoutError(f"fal-flux job did not complete within {timeout_s}s")

    def generate_image(
        self,
        scene: Scene,
        cfg: GenerationConfig,
        *,
        characters: Optional[list[Character]] = None,
        control_image: Optional[Path] = None,
    ) -> Artifact:
        payload = self.build_input(scene, cfg)
        submit = self._submit(payload)
        result = self._await_result(submit["status_url"], submit["response_url"])
        images = result.get("images") or []
        if not images or not images[0].get("url"):
            raise RuntimeError(f"fal-flux result has no image url: {result}")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.output_dir / f"flux_s{scene.index}.png"
        with httpx.Client(timeout=120.0) as client:
            out_path.write_bytes(client.get(images[0]["url"]).content)
        log.info("fal-flux scene %d image saved -> %s", scene.index, out_path.name)
        return Artifact(path=out_path, kind="image", scene_index=scene.index, meta={"engine": "fal-flux", "model": self.model})
