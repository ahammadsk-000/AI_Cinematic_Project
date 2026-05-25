"""ComfyUIAnimateDiffBackend — image -> short animated clip via ComfyUI AnimateDiff.

Mirrors the ComfyUI image backend pattern: pure HTTP, drives a running ComfyUI
server with an AnimateDiff workflow JSON, polls /history, downloads the produced
frames/gif/mp4 via /view. Heavy diffusion runs inside ComfyUI (which manages
offload), so this adapter holds no VRAM itself.

Generates SHORT windows (cfg.frames_per_clip) per scene — never the whole video at
once — which is the §6 low-VRAM rule for motion models on a T4.
"""

from __future__ import annotations

import copy
import json
import random
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx

from ai_engine.config import EngineConfig
from ai_engine.interfaces import AnimationBackend, Artifact, GenerationConfig, Scene
from ai_engine.utils.logging import get_logger
from ai_engine.utils.retry import retry

log = get_logger("animatediff")

_WORKFLOW_DIR = Path(__file__).resolve().parents[4] / "comfyui" / "workflows"


class ComfyUIAnimateDiffBackend(AnimationBackend):
    def __init__(self, server_url: str, workflow: str = "animatediff", workflow_dir: Optional[Path] = None) -> None:
        self.server_url = server_url.rstrip("/")
        self.workflow_name = workflow
        self.workflow_dir = workflow_dir or _WORKFLOW_DIR
        self.client_id = uuid.uuid4().hex
        self.output_dir = Path.cwd()
        self._loaded = False
        self._template: dict[str, Any] | None = None
        self._node_map: dict[str, Any] | None = None

    @classmethod
    def from_config(cls, cfg: EngineConfig) -> "ComfyUIAnimateDiffBackend":
        return cls(cfg.comfyui_url)

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load_workflow(self) -> None:
        self._template = json.loads((self.workflow_dir / f"{self.workflow_name}.json").read_text("utf-8"))
        node_maps = json.loads((self.workflow_dir / "node_map.json").read_text("utf-8"))
        self._node_map = node_maps[self.workflow_name]

    @retry(attempts=5, backoff=2.0, exceptions=(httpx.HTTPError,))
    def load(self) -> None:
        with httpx.Client(timeout=10.0) as client:
            client.get(f"{self.server_url}/system_stats").raise_for_status()
        self.load_workflow()
        self._loaded = True

    def unload(self) -> None:
        if not self._loaded:
            return
        try:
            with httpx.Client(timeout=10.0) as client:
                client.post(f"{self.server_url}/free", json={"unload_models": True, "free_memory": True})
        except httpx.HTTPError as exc:
            log.warning("ComfyUI /free failed: %s", exc)
        self._loaded = False

    def _set(self, graph: dict, logical: str, value: Any) -> None:
        assert self._node_map is not None
        mapping = self._node_map.get(logical)
        if isinstance(mapping, list):
            node_id, key = mapping
            graph[node_id]["inputs"][key] = value

    def build_graph(self, image: Artifact, scene: Scene, cfg: GenerationConfig) -> dict:
        assert self._template is not None
        graph = copy.deepcopy(self._template)
        graph.pop("_meta", None)
        seed = cfg.seed if cfg.seed is not None else random.randint(0, 2**32 - 1)
        self._set(graph, "init_image", image.path.name)   # ComfyUI LoadImage by name
        self._set(graph, "positive", scene.prompt)
        self._set(graph, "negative", scene.negative_prompt)
        self._set(graph, "frames", cfg.frames_per_clip)
        self._set(graph, "fps", cfg.fps)
        self._set(graph, "seed", seed)
        self._set(graph, "motion", scene.motion or scene.camera)
        return graph

    def animate(self, image: Artifact, scene: Scene, cfg: GenerationConfig) -> Artifact:
        if not self._loaded:
            self.load()
        graph = self.build_graph(image, scene, cfg)
        prompt_id = self._queue(graph)
        meta = self._await_output(prompt_id)
        out_path = self._download(meta, scene)
        return Artifact(path=out_path, kind="video", scene_index=scene.index, meta={"prompt_id": prompt_id})

    @retry(attempts=3, backoff=2.0, exceptions=(httpx.HTTPError,))
    def _queue(self, graph: dict) -> str:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{self.server_url}/prompt", json={"prompt": graph, "client_id": self.client_id})
            resp.raise_for_status()
            return resp.json()["prompt_id"]

    def _await_output(self, prompt_id: str, *, timeout_s: float = 900.0, poll_s: float = 2.0) -> dict:
        deadline = time.time() + timeout_s
        with httpx.Client(timeout=30.0) as client:
            while time.time() < deadline:
                resp = client.get(f"{self.server_url}/history/{prompt_id}")
                resp.raise_for_status()
                entry = resp.json().get(prompt_id)
                if entry and "outputs" in entry:
                    for node_out in entry["outputs"].values():
                        for key in ("gifs", "videos", "images"):
                            if node_out.get(key):
                                return node_out[key][0]
                time.sleep(poll_s)
        raise TimeoutError(f"AnimateDiff prompt {prompt_id} did not finish within {timeout_s}s")

    def _download(self, meta: dict, scene: Scene) -> Path:
        params = {"filename": meta["filename"], "subfolder": meta.get("subfolder", ""), "type": meta.get("type", "output")}
        with httpx.Client(timeout=120.0) as client:
            resp = client.get(f"{self.server_url}/view", params=params)
            resp.raise_for_status()
            data = resp.content
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.output_dir / f"clip_s{scene.index}_{meta['filename']}"
        out_path.write_bytes(data)
        return out_path
