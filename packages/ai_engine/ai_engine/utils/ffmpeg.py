"""Locate an ffmpeg binary. Prefers the one bundled by imageio-ffmpeg (always
available once that wheel is installed, even on Colab/Kaggle), falls back to a
system ffmpeg on PATH."""

from __future__ import annotations

import functools
import shutil


@functools.lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg  # noqa: PLC0415

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return shutil.which("ffmpeg") or "ffmpeg"
