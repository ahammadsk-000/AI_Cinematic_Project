"""KenBurnsAnimationBackend — zero-GPU motion via ffmpeg.

The cheapest, most reliable way to get cinematic motion on a free tier: apply a
simulated camera move (zoom / pan) to a still image with ffmpeg's zoompan filter.
No diffusion model, no VRAM. This is the DEFAULT animation backend so the pipeline
always produces video even when AnimateDiff/SVD won't fit in memory.

The camera move is chosen from the scene's `motion`/`camera` hints.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from ai_engine.config import EngineConfig
from ai_engine.interfaces import AnimationBackend, Artifact, GenerationConfig, Scene
from ai_engine.utils.ffmpeg import ffmpeg_exe
from ai_engine.utils.logging import get_logger

log = get_logger("kenburns")


class KenBurnsAnimationBackend(AnimationBackend):
    def __init__(self) -> None:
        self.output_dir = Path.cwd()

    @classmethod
    def from_config(cls, _cfg: EngineConfig) -> "KenBurnsAnimationBackend":
        return cls()

    # No model to hold — lifecycle is a no-op (still satisfies the contract).
    @property
    def is_loaded(self) -> bool:
        return True

    def load(self) -> None:  # noqa: D401
        pass

    def unload(self) -> None:
        pass

    def _move(self, scene: Scene) -> str:
        """Pick a zoompan expression from the scene's camera/motion hints."""
        hint = f"{scene.camera} {scene.motion}".lower()
        if "pan" in hint or "tracking" in hint:
            # slow horizontal pan
            return "zoom='min(zoom+0.0005,1.2)':x='iw/2-(iw/zoom/2)+on*2':y='ih/2-(ih/zoom/2)'"
        if "out" in hint or "reveal" in hint or "wide" in hint:
            # zoom out
            return "zoom='if(eq(on,1),1.3,max(1.001,zoom-0.0008))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        # default: slow zoom in (push)
        return "zoom='min(zoom+0.0008,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

    def build_command(self, image: Artifact, scene: Scene, cfg: GenerationConfig, out_path: Path) -> list[str]:
        """Pure: assemble the ffmpeg argv (no execution) — unit-testable."""
        frames = max(1, int(round(scene.duration_sec * cfg.fps)))
        zoompan = self._move(scene)
        vf = (
            f"scale={cfg.width * 2}:-1,"  # supersample so zoom stays sharp
            f"zoompan={zoompan}:d={frames}:s={cfg.width}x{cfg.height}:fps={cfg.fps},"
            f"format=yuv420p"
        )
        return [
            ffmpeg_exe(), "-y", "-loop", "1", "-i", str(image.path),
            "-vf", vf, "-t", f"{scene.duration_sec:.2f}", "-r", str(cfg.fps),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path),
        ]

    def animate(self, image: Artifact, scene: Scene, cfg: GenerationConfig) -> Artifact:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.output_dir / f"clip_s{scene.index}.mp4"
        cmd = self.build_command(image, scene, cfg, out_path)
        log.info("ken-burns clip scene %d (%ds @ %dfps)", scene.index, scene.duration_sec, cfg.fps)
        subprocess.run(cmd, check=True, capture_output=True)
        return Artifact(path=out_path, kind="video", scene_index=scene.index, meta={"motion": "kenburns"})
