"""GTTSBackend — multilingual narration via gTTS (Google Translate TTS).

Why this exists: XTTS v2 doesn't support many Indian languages (e.g. Telugu), and
Coqui TTS / audiocraft don't install on Python 3.12 (Colab's runtime). gTTS is a
tiny, free, no-GPU dependency that covers 50+ languages including Telugu (`te`),
Hindi (`hi`), Tamil (`ta`), etc. — making it the most reliable narration path on a
constrained Colab kernel.

It outputs mp3; we transcode to wav with ffmpeg so the composer can concat it like
any other audio track. Falls back to a silent track if gTTS is unavailable/offline.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from ai_engine.config import EngineConfig
from ai_engine.interfaces import Artifact, VoiceBackend
from ai_engine.utils.ffmpeg import ffmpeg_exe
from ai_engine.utils.logging import get_logger

log = get_logger("gtts")


class GTTSBackend(VoiceBackend):
    def __init__(self, language: str = "en") -> None:
        self.language = language          # e.g. "te" (Telugu), "hi", "en"
        self.output_dir = Path.cwd()

    @classmethod
    def from_config(cls, cfg: EngineConfig) -> "GTTSBackend":
        return cls(language=getattr(cfg, "voice_lang", "en"))

    # No model to hold in VRAM — lifecycle is a no-op.
    @property
    def is_loaded(self) -> bool:
        return True

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def synthesize(
        self,
        text: str,
        *,
        voice: str = "narrator",
        language: Optional[str] = None,
        emotion: str = "neutral",
        out_path: Optional[Path] = None,
    ) -> Artifact:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_path or (self.output_dir / "narration.wav")
        lang = language or self.language

        if not text.strip():
            self._silence(out_path, seconds=1.0)
            return Artifact(path=out_path, kind="audio", meta={"silent": True})

        try:
            from gtts import gTTS  # noqa: PLC0415

            mp3 = out_path.with_suffix(".mp3")
            gTTS(text=text, lang=lang, slow=False).save(str(mp3))
            # transcode mp3 -> wav (24kHz mono) so it concats cleanly with other tracks
            subprocess.run(
                [ffmpeg_exe(), "-y", "-i", str(mp3), "-ar", "24000", "-ac", "1", str(out_path)],
                check=True, capture_output=True,
            )
            log.info("narration synthesized via gTTS (%d chars, lang=%s)", len(text), lang)
            return Artifact(path=out_path, kind="audio", meta={"lang": lang, "engine": "gtts"})
        except Exception as exc:  # noqa: BLE001 - offline / unsupported lang
            log.warning("gTTS failed (%s); narration will be silent", exc)
            self._silence(out_path, seconds=max(1.0, len(text) / 14))
            return Artifact(path=out_path, kind="audio", meta={"silent": True})

    def _silence(self, out_path: Path, *, seconds: float) -> None:
        subprocess.run(
            [ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
             "-t", f"{seconds:.2f}", "-q:a", "9", str(out_path)],
            check=True, capture_output=True,
        )
