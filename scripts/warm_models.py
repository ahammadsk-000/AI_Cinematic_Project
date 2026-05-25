"""Pre-download / warm models so the first job isn't slow.

Run on the GPU box after boot (the notebooks can call this):

    python scripts/warm_models.py

Warms, in order of impact:
  * the Ollama LLM (pull),
  * the SDXL base checkpoint into ComfyUI (if missing),
  * optionally the XTTS + MusicGen weights via a tiny dry-run.

Everything is best-effort and idempotent — already-present models are skipped.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def warm_ollama() -> None:
    model = os.getenv("CINEFORGE_LLM_MODEL", "llama3")
    print(f"[warm] ollama pull {model}")
    subprocess.run(["ollama", "pull", model], check=False)


def warm_sdxl() -> None:
    target = Path("comfyui/ComfyUI/models/checkpoints/sd_xl_base_1.0.safetensors")
    if target.exists():
        print("[warm] SDXL base already present")
        return
    url = "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
    target.parent.mkdir(parents=True, exist_ok=True)
    print("[warm] downloading SDXL base checkpoint (~6.9 GB)…")
    subprocess.run(["wget", "-nc", "-q", "-O", str(target), url], check=False)


def warm_audio() -> None:
    """Trigger the lazy weight downloads for XTTS + MusicGen without rendering."""
    try:
        from TTS.api import TTS  # noqa: F401, PLC0415

        print("[warm] XTTS import ok (weights download on first synth)")
    except Exception as exc:  # noqa: BLE001
        print(f"[warm] XTTS not available: {exc}")
    try:
        from audiocraft.models import MusicGen  # noqa: PLC0415

        MusicGen.get_pretrained("facebook/musicgen-small")
        print("[warm] MusicGen-small ready")
    except Exception as exc:  # noqa: BLE001
        print(f"[warm] MusicGen not available: {exc}")


def main() -> int:
    warm_ollama()
    warm_sdxl()
    warm_audio()
    print("[warm] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
