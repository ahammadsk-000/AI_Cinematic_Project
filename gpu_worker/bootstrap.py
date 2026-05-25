"""Boot a local ComfyUI server on the GPU box (Colab/Kaggle/local).

Full model-download wiring lands with the Phase 6 notebooks; this provides the
programmatic hook. It clones/launches ComfyUI if not already running and waits for
its HTTP API to come up.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import httpx

from ai_engine.config import load_config
from ai_engine.utils.logging import get_logger

log = get_logger("bootstrap")

_COMFY_DIR = Path("comfyui/ComfyUI")


def _is_up(url: str) -> bool:
    try:
        httpx.get(f"{url}/system_stats", timeout=2.0).raise_for_status()
        return True
    except Exception:  # noqa: BLE001
        return False


def ensure_comfyui(timeout_s: float = 180.0) -> str:
    """Return the ComfyUI URL once reachable, launching it if necessary."""
    cfg = load_config()
    url = cfg.comfyui_url
    if _is_up(url):
        log.info("ComfyUI already running at %s", url)
        return url

    if not _COMFY_DIR.exists():
        log.info("cloning ComfyUI…")
        subprocess.run(["git", "clone", "https://github.com/comfyanonymous/ComfyUI.git", str(_COMFY_DIR)], check=True)
        subprocess.run(["pip", "install", "-r", str(_COMFY_DIR / "requirements.txt")], check=True)

    log.info("launching ComfyUI…")
    subprocess.Popen(["python", "main.py", "--listen", "127.0.0.1", "--port", "8188"], cwd=str(_COMFY_DIR))

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _is_up(url):
            log.info("ComfyUI is up at %s", url)
            return url
        time.sleep(3)
    raise TimeoutError("ComfyUI did not start in time")
