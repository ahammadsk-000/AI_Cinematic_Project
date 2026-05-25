"""FalVideoBackend — OPTIONAL paid img2vid via fal.ai (Kling / Hailuo / etc.).

This is a fully self-contained, additive AnimationBackend. It animates the SDXL
still through a frontier video model on fal.ai's servers (so it needs NO local
GPU/VRAM — the heavy lifting is remote). Enable it with:

    CINEFORGE_ANIM_BACKEND=fal
    FAL_KEY=<your fal.ai key>
    FAL_VIDEO_MODEL=fal-ai/kling-video/v1.6/standard/image-to-video   # optional override

To go back to the free path, just set CINEFORGE_ANIM_BACKEND=kenburns (or svd).
Nothing else in the pipeline depends on this file.

Uses fal's async queue REST API over httpx (no extra package). The still is sent
inline as a base64 data URI, so this module has no dependency on the worker's
storage layer.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Optional

import httpx

from ai_engine.interfaces import AnimationBackend, Artifact, GenerationConfig, Scene
from ai_engine.utils.logging import get_logger
from ai_engine.utils.retry import retry

log = get_logger("fal")

_DEFAULT_MODEL = "fal-ai/kling-video/v1.6/standard/image-to-video"
_QUEUE_BASE = "https://queue.fal.run"


class FalVideoBackend(AnimationBackend):
    def __init__(self, model: str, api_key: str, duration: str = "5") -> None:
        self.model = model
        self.api_key = api_key
        self.duration = duration            # Kling accepts "5" or "10" (seconds)
        self.output_dir = Path.cwd()

    @classmethod
    def from_config(cls, cfg) -> "FalVideoBackend":  # cfg: EngineConfig (duck-typed)
        key = os.getenv("FAL_KEY", "")
        if not key:
            raise ValueError("FAL_KEY is not set — required for CINEFORGE_ANIM_BACKEND=fal")
        return cls(
            model=os.getenv("FAL_VIDEO_MODEL", _DEFAULT_MODEL),
            api_key=key,
            duration=os.getenv("FAL_VIDEO_DURATION", "5"),
        )

    # remote API → no local model to hold; lifecycle is a no-op
    @property
    def is_loaded(self) -> bool:
        return True

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    # --- helpers ---------------------------------------------------------- #
    def _headers(self) -> dict:
        return {"Authorization": f"Key {self.api_key}", "Content-Type": "application/json"}

    @staticmethod
    def _data_uri(path: Path) -> str:
        b64 = base64.b64encode(Path(path).read_bytes()).decode()
        return f"data:image/png;base64,{b64}"

    def build_input(self, image: Artifact, scene: Scene, cfg: GenerationConfig) -> dict:
        """Pure: the fal request payload (no network) — unit-testable."""
        motion = " ".join(p for p in (scene.summary, scene.motion, scene.camera) if p).strip()
        return {
            "prompt": motion or "subtle cinematic motion",
            "image_url": self._data_uri(image.path),
            "duration": self.duration,
            "aspect_ratio": cfg.aspect_ratio.value,  # "16:9" | "9:16" | "1:1"
        }

    # --- generation ------------------------------------------------------- #
    @retry(attempts=3, backoff=3.0, exceptions=(httpx.HTTPError,))
    def _submit(self, payload: dict) -> dict:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{_QUEUE_BASE}/{self.model}", json=payload, headers=self._headers())
            if resp.status_code >= 400:
                # surface fal's actual reason (e.g. "Exhausted balance", bad key, bad model)
                log.error("fal %s on %s -> %s", resp.status_code, self.model, resp.text[:400])
            resp.raise_for_status()
            return resp.json()   # {request_id, status_url, response_url, ...}

    def _await_result(self, status_url: str, response_url: str, *, timeout_s: float = 600.0, poll_s: float = 4.0) -> dict:
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
                    raise RuntimeError(f"fal job failed: {st.json()}")
                time.sleep(poll_s)
        raise TimeoutError(f"fal job did not complete within {timeout_s}s")

    def animate(self, image: Artifact, scene: Scene, cfg: GenerationConfig) -> Artifact:
        payload = self.build_input(image, scene, cfg)
        log.info("fal img2vid scene %d via %s", scene.index, self.model)
        submit = self._submit(payload)
        result = self._await_result(submit["status_url"], submit["response_url"])

        video_url = (result.get("video") or {}).get("url") or result.get("url")
        if not video_url:
            raise RuntimeError(f"fal result has no video url: {result}")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.output_dir / f"clip_s{scene.index}.mp4"
        with httpx.Client(timeout=180.0) as client:
            data = client.get(video_url).content
        out_path.write_bytes(data)
        log.info("fal clip scene %d saved -> %s", scene.index, out_path.name)
        return Artifact(path=out_path, kind="video", scene_index=scene.index, meta={"engine": "fal", "model": self.model})
