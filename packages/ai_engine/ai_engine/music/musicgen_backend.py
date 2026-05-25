"""MusicGenBackend — cinematic background score via Meta's MusicGen (AudioCraft).

Generates a score from a text mood description (e.g. "melancholic synthwave,
suspenseful"). Lazy torch/audiocraft imports confined to load(). Falls back to a
silent track if AudioCraft isn't installed so compose never fails.

Low-VRAM: defaults to the `small` model (≈1.5 GB) which fits comfortably alongside
the rest on a T4; configurable up to `medium` when VRAM allows.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Optional

from ai_engine.config import EngineConfig
from ai_engine.interfaces import Artifact, MusicBackend
from ai_engine.utils.ffmpeg import ffmpeg_exe
from ai_engine.utils.logging import get_logger
from ai_engine.utils.vram import empty_cache

log = get_logger("musicgen")

# 30s is MusicGen's sweet spot; longer durations are generated then looped/trimmed.
_MAX_SEGMENT_S = 30.0


class MusicGenBackend(MusicBackend):
    def __init__(self, cfg: EngineConfig, model_size: str = "small") -> None:
        self.cfg = cfg
        self.model_size = model_size
        self.output_dir = Path.cwd()
        self._model: Any = None

    @classmethod
    def from_config(cls, cfg: EngineConfig) -> "MusicGenBackend":
        return cls(cfg)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return
        try:
            from audiocraft.models import MusicGen  # noqa: PLC0415

            self._model = MusicGen.get_pretrained(f"facebook/musicgen-{self.model_size}")
            log.info("MusicGen-%s loaded", self.model_size)
        except Exception as exc:  # noqa: BLE001
            log.warning("MusicGen unavailable (%s); score will be silent", exc)
            self._model = False

    def unload(self) -> None:
        if self._model not in (None, False):
            del self._model
            empty_cache()
        self._model = None

    def compose_music(self, mood: str, *, duration_sec: float, out_path: Optional[Path] = None) -> Artifact:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_path or (self.output_dir / "score.wav")
        if self._model is None:
            self.load()

        if not self._model:
            self._silence(out_path, seconds=duration_sec)
            return Artifact(path=out_path, kind="audio", meta={"silent": True})

        import torchaudio  # noqa: PLC0415

        segment = min(duration_sec, _MAX_SEGMENT_S)
        self._model.set_generation_params(duration=segment)
        wav = self._model.generate([mood or "cinematic ambient score"])[0].cpu()
        torchaudio.save(str(out_path), wav, self._model.sample_rate)
        log.info("score generated (%.1fs base for mood='%s')", segment, mood)

        # If the video is longer than one segment, loop the track to fit.
        if duration_sec > segment:
            looped = out_path.with_name("score_looped.wav")
            self._loop_to(out_path, looped, duration_sec)
            out_path = looped
        return Artifact(path=out_path, kind="audio", meta={"mood": mood})

    def _loop_to(self, src: Path, dst: Path, seconds: float) -> None:
        cmd = [ffmpeg_exe(), "-y", "-stream_loop", "-1", "-i", str(src), "-t", f"{seconds:.2f}", "-c", "copy", str(dst)]
        subprocess.run(cmd, check=True, capture_output=True)

    def _silence(self, out_path: Path, *, seconds: float) -> None:
        cmd = [ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "anullsrc=r=32000:cl=stereo", "-t", f"{seconds:.2f}", str(out_path)]
        subprocess.run(cmd, check=True, capture_output=True)
