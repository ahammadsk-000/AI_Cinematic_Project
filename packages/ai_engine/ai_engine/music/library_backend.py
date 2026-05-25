"""LibraryMusicBackend — reliable background music with no heavy deps.

Two sources, in order:
  1. A real royalty-free track from a music directory, picked by the scene's mood
     (drop your own CC0 .mp3/.wav files named like "emotional.mp3", "suspense.mp3"
     into <music_dir>; the file is looped/trimmed to the video length).
  2. If no track is found, a generated WARM AMBIENT PAD synthesized with ffmpeg
     (mood-tuned chord of soft sine tones + tremolo + low-pass + fades). This needs
     no models, no network, no GPU — so there is ALWAYS audible background music.

This is the dependable alternative to MusicGen (audiocraft), which doesn't install
on Colab's Python 3.12. Every ffmpeg invocation is a pure `build_*` method so the
commands are unit-testable without ffmpeg.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from ai_engine.config import EngineConfig
from ai_engine.interfaces import Artifact, MusicBackend
from ai_engine.utils.ffmpeg import ffmpeg_exe
from ai_engine.utils.logging import get_logger

log = get_logger("music")

_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}

# Mood -> soft low chord (Hz). Substring-matched against the scene's music_mood.
_MOOD_CHORDS: dict[str, list[float]] = {
    "sad": [130.81, 155.56, 196.00],          # C minor — melancholic
    "melanchol": [130.81, 155.56, 196.00],
    "emotional": [130.81, 164.81, 196.00],    # C major — warm
    "warm": [130.81, 164.81, 196.00],
    "happy": [196.00, 246.94, 293.66],        # G major — bright
    "cheer": [196.00, 246.94, 293.66],
    "uplift": [196.00, 246.94, 293.66],
    "epic": [65.41, 130.81, 196.00, 329.63],  # full cinematic stack
    "cinematic": [65.41, 130.81, 196.00, 261.63],
    "suspense": [65.41, 92.50],               # low + tritone — tense
    "tense": [65.41, 92.50],
    "dark": [65.41, 92.50],
    "action": [98.00, 146.83, 196.00],        # driving (tremolo gives pulse)
}
_DEFAULT_CHORD = [130.81, 196.00, 261.63]      # neutral ambient


class LibraryMusicBackend(MusicBackend):
    def __init__(self, music_dir: Optional[Path] = None) -> None:
        self.music_dir = Path(music_dir) if music_dir else None
        self.output_dir = Path.cwd()

    @classmethod
    def from_config(cls, cfg: EngineConfig) -> "LibraryMusicBackend":
        return cls(music_dir=getattr(cfg, "music_dir", None))

    # no model to hold — lifecycle is a no-op
    @property
    def is_loaded(self) -> bool:
        return True

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    # --- mood -> resources ------------------------------------------------ #
    def _find_track(self, mood: str) -> Optional[Path]:
        if not self.music_dir or not self.music_dir.is_dir():
            return None
        files = [p for p in self.music_dir.iterdir() if p.suffix.lower() in _AUDIO_EXTS]
        if not files:
            return None
        mood_l = mood.lower()
        # prefer a file whose name shares a word with the mood, else the first track
        for p in files:
            if any(tok and tok in p.stem.lower() for tok in mood_l.split()):
                return p
        return files[0]

    @staticmethod
    def _chord_for(mood: str) -> list[float]:
        mood_l = (mood or "").lower()
        for key, freqs in _MOOD_CHORDS.items():
            if key in mood_l:
                return freqs
        return _DEFAULT_CHORD

    # --- pure command builders (testable) -------------------------------- #
    @staticmethod
    def build_loop_command(track: Path, out_path: Path, duration: float) -> list[str]:
        return [
            ffmpeg_exe(), "-y", "-stream_loop", "-1", "-i", str(track),
            "-t", f"{duration:.2f}",
            "-af", "afade=t=in:d=2,afade=t=out:st=%.2f:d=2,volume=0.8" % max(0.0, duration - 2),
            "-ac", "2", "-ar", "44100", str(out_path),
        ]

    def build_procedural_command(self, freqs: list[float], duration: float, out_path: Path) -> list[str]:
        inputs: list[str] = []
        for f in freqs:
            inputs += ["-f", "lavfi", "-i", f"sine=frequency={f}:duration={duration:.2f}"]
        labels = "".join(f"[{i}:a]" for i in range(len(freqs)))
        fade_out_at = max(0.0, duration - 2)
        filt = (
            f"{labels}amix=inputs={len(freqs)}:normalize=1,"
            f"tremolo=f=5:d=0.4,lowpass=f=900,"
            f"afade=t=in:d=2,afade=t=out:st={fade_out_at:.2f}:d=2,"
            f"volume=0.9,aformat=channel_layouts=stereo"
        )
        return [ffmpeg_exe(), "-y", *inputs, "-filter_complex", filt, "-ar", "44100", str(out_path)]

    # --- main ------------------------------------------------------------- #
    def compose_music(self, mood: str, *, duration_sec: float, out_path: Optional[Path] = None) -> Artifact:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_path or (self.output_dir / "score.wav")
        duration_sec = max(1.0, duration_sec)

        track = self._find_track(mood)
        if track is not None:
            subprocess.run(self.build_loop_command(track, out_path, duration_sec), check=True, capture_output=True)
            log.info("score from library track '%s' (mood='%s')", track.name, mood)
            return Artifact(path=out_path, kind="audio", meta={"source": "library", "track": track.name})

        freqs = self._chord_for(mood)
        subprocess.run(self.build_procedural_command(freqs, duration_sec, out_path), check=True, capture_output=True)
        log.info("score generated (procedural pad, mood='%s', %.1fs)", mood, duration_sec)
        return Artifact(path=out_path, kind="audio", meta={"source": "procedural", "mood": mood})
