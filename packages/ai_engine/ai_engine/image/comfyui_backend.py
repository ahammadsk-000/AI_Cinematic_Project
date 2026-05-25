"""ComfyUIImageBackend — the PRIMARY image adapter.

Drives a running ComfyUI server over its HTTP API:
  1. load a workflow JSON template + its node-map,
  2. inject prompt / negative / seed / size / steps / cfg into the right nodes,
  3. POST /prompt to queue, poll /history/{id} until done,
  4. download the produced image via /view and save it to the job dir.

ComfyUI handles its own model offloading (the key low-VRAM win), so load()/
unload() here are light: load() verifies connectivity; unload() asks the server
to free model memory via /free between heavy stages.

No torch import — this adapter is pure HTTP and runs even on the CPU box (useful
for tests). The actual diffusion happens inside the ComfyUI process.
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
from ai_engine.interfaces import Artifact, Character, GenerationConfig, ImageBackend, Scene
from ai_engine.utils.logging import get_logger
from ai_engine.utils.retry import retry

log = get_logger("comfyui")

# repo-root comfyui/workflows/ relative to this file (packages/ai_engine/ai_engine/image/)
_WORKFLOW_DIR = Path(__file__).resolve().parents[4] / "comfyui" / "workflows"


class ComfyUIImageBackend(ImageBackend):
    def __init__(self, server_url: str, workflow: str = "sdxl_txt2img", workflow_dir: Optional[Path] = None) -> None:
        self.server_url = server_url.rstrip("/")
        self.workflow_name = workflow
        self.workflow_dir = workflow_dir or _WORKFLOW_DIR
        self.client_id = uuid.uuid4().hex
        #: where downloaded images are written; the orchestrator points this at the job dir
        self.output_dir = Path.cwd()
        self._loaded = False
        self._template: dict[str, Any] | None = None
        self._node_map: dict[str, Any] | None = None

    @classmethod
    def from_config(cls, cfg: EngineConfig) -> "ComfyUIImageBackend":
        return cls(cfg.comfyui_url)

    # --- lifecycle -------------------------------------------------------- #
    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load_workflow(self) -> None:
        """Read & cache the workflow template + node-map from disk. No network —
        kept separate from load() so graph-building is unit-testable offline."""
        self._template = json.loads((self.workflow_dir / f"{self.workflow_name}.json").read_text("utf-8"))
        node_maps = json.loads((self.workflow_dir / "node_map.json").read_text("utf-8"))
        self._node_map = node_maps[self.workflow_name]

    @retry(attempts=5, backoff=2.0, exceptions=(httpx.HTTPError,))
    def load(self) -> None:
        """Verify the ComfyUI server is reachable and cache the workflow files."""
        with httpx.Client(timeout=10.0) as client:
            client.get(f"{self.server_url}/system_stats").raise_for_status()
        self.load_workflow()
        self._loaded = True
        log.info("ComfyUI backend ready (%s, workflow=%s)", self.server_url, self.workflow_name)

    def unload(self) -> None:
        """Ask ComfyUI to free model memory so the next heavy stage has VRAM."""
        if not self._loaded:
            return
        try:
            with httpx.Client(timeout=10.0) as client:
                client.post(f"{self.server_url}/free", json={"unload_models": True, "free_memory": True})
        except httpx.HTTPError as exc:  # best-effort
            log.warning("ComfyUI /free failed: %s", exc)
        self._loaded = False

    # --- generation ------------------------------------------------------- #
    def generate_image(
        self,
        scene: Scene,
        cfg: GenerationConfig,
        *,
        characters: Optional[list[Character]] = None,
        control_image: Optional[Path] = None,
    ) -> Artifact:
        if not self._loaded:
            self.load()
        graph = self._build_graph(scene, cfg)
        prompt_id = self._queue(graph)
        image_meta = self._await_image(prompt_id)
        out_path = self._download(image_meta, scene)
        return Artifact(path=out_path, kind="image", scene_index=scene.index, meta={"prompt_id": prompt_id})

    # --- internals -------------------------------------------------------- #
    def _set(self, graph: dict, logical: str, value: Any) -> None:
        assert self._node_map is not None
        mapping = self._node_map.get(logical)
        if not isinstance(mapping, list):
            return
        node_id, input_key = mapping
        graph[node_id]["inputs"][input_key] = value

    def _build_graph(self, scene: Scene, cfg: GenerationConfig) -> dict:
        assert self._template is not None
        graph = copy.deepcopy(self._template)
        graph.pop("_meta", None)
        seed = cfg.seed if cfg.seed is not None else random.randint(0, 2**32 - 1)
        self._set(graph, "positive", scene.prompt)
        self._set(graph, "negative", scene.negative_prompt)
        self._set(graph, "width", cfg.width)
        self._set(graph, "height", cfg.height)
        self._set(graph, "seed", seed)
        self._set(graph, "steps", cfg.steps)
        self._set(graph, "cfg", cfg.cfg_scale)
        self._set(graph, "filename_prefix", f"cineforge_s{scene.index}")
        return graph

    @retry(attempts=3, backoff=2.0, exceptions=(httpx.HTTPError,))
    def _queue(self, graph: dict) -> str:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{self.server_url}/prompt", json={"prompt": graph, "client_id": self.client_id})
            resp.raise_for_status()
            return resp.json()["prompt_id"]

    def _await_image(self, prompt_id: str, *, timeout_s: float = 600.0, poll_s: float = 1.5) -> dict:
        """Poll /history until the prompt completes; return the first SaveImage output."""
        deadline = time.time() + timeout_s
        with httpx.Client(timeout=30.0) as client:
            while time.time() < deadline:
                resp = client.get(f"{self.server_url}/history/{prompt_id}")
                resp.raise_for_status()
                history = resp.json()
                entry = history.get(prompt_id)
                if entry and "outputs" in entry:
                    for node_out in entry["outputs"].values():
                        if node_out.get("images"):
                            return node_out["images"][0]
                time.sleep(poll_s)
        raise TimeoutError(f"ComfyUI prompt {prompt_id} did not finish within {timeout_s}s")

    def _download(self, image_meta: dict, scene: Scene) -> Path:
        params = {
            "filename": image_meta["filename"],
            "subfolder": image_meta.get("subfolder", ""),
            "type": image_meta.get("type", "output"),
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.get(f"{self.server_url}/view", params=params)
            resp.raise_for_status()
            data = resp.content
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.output_dir / image_meta["filename"]
        out_path.write_bytes(data)
        log.info("scene %d image saved -> %s", scene.index, out_path.name)
        return out_path
