"""XTTSBackend — narration synthesis via Coqui XTTS v2 (default voice adapter).

Emotional, multilingual, supports voice cloning from a short reference clip. All
Coqui/torch imports are lazy + confined to load(). If TTS isn't installed (or the
model can't download), synthesize() degrades to a silent track of the right length
via ffmpeg so the compose stage still succeeds.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Optional

from ai_engine.config import EngineConfig
from ai_engine.interfaces import Artifact, VoiceBackend
from ai_engine.utils.ffmpeg import ffmpeg_exe
from ai_engine.utils.logging import get_logger
from ai_engine.utils.vram import empty_cache

log = get_logger("xtts")

_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"

# Built-in speaker presets -> Coqui speaker names (overridable via voice= arg).
_VOICE_PRESETS = {
    "narrator_male": "Damien Black",
    "narrator_female": "Claribel Dervla",
}


class XTTSBackend(VoiceBackend):
    def __init__(self, cfg: EngineConfig, speaker_wav: Optional[Path] = None) -> None:
        self.cfg = cfg
        self.speaker_wav = speaker_wav  # optional voice-clone reference
        self.output_dir = Path.cwd()
        self._tts: Any = None

    @classmethod
    def from_config(cls, cfg: EngineConfig) -> "XTTSBackend":
        return cls(cfg)

    @property
    def is_loaded(self) -> bool:
        return self._tts is not None

    def load(self) -> None:
        if self._tts is not None:
            return
        try:
            import torch  # noqa: PLC0415
            from TTS.api import TTS  # noqa: PLC0415

            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._tts = TTS(_MODEL).to(device)
            log.info("XTTS v2 loaded on %s", device)
        except Exception as exc:  # noqa: BLE001 - optional/large dependency
            log.warning("XTTS unavailable (%s); narration will be silent", exc)
            self._tts = False  # sentinel: tried and failed

    def unload(self) -> None:
        if self._tts not in (None, False):
            del self._tts
            empty_cache()
        self._tts = None

    def synthesize(
        self,
        text: str,
        *,
        voice: str = "narrator_male",
        language: str = "en",
        emotion: str = "neutral",
        out_path: Optional[Path] = None,
    ) -> Artifact:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_path or (self.output_dir / "narration.wav")
        if self._tts is None:
            self.load()

        if not self._tts or not text.strip():
            self._silence(out_path, seconds=max(1.0, len(text) / 14))  # ~14 chars/sec speech
            return Artifact(path=out_path, kind="audio", meta={"silent": True})

        speaker = _VOICE_PRESETS.get(voice, voice)
        kwargs: dict[str, Any] = {"text": text, "language": language, "file_path": str(out_path)}
        if self.speaker_wav:
            kwargs["speaker_wav"] = str(self.speaker_wav)
        else:
            kwargs["speaker"] = speaker
        self._tts.tts_to_file(**kwargs)
        log.info("narration synthesized (%d chars, voice=%s)", len(text), voice)
        return Artifact(path=out_path, kind="audio", meta={"voice": voice, "language": language})

    def _silence(self, out_path: Path, *, seconds: float) -> None:
        cmd = [
            ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", f"{seconds:.2f}", "-q:a", "9", str(out_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
