"""FFmpegComposer — final assembly into an MP4 (default Composer adapter).

Pipeline:
  1. concat the per-scene clips (concat demuxer),
  2. build an SRT from per-scene narration timings and burn it in,
  3. mix narration (spoken, foreground) with music (ducked background),
  4. letterbox/crop to the target aspect ratio, export H.264 + AAC.

Each ffmpeg invocation is assembled by a pure `build_*` method that returns argv
(no execution), so command construction is fully unit-testable without ffmpeg.
The exported MP4 is YouTube- and Reels-ready depending on aspect ratio.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ai_engine.interfaces import Artifact, AspectRatio, Composer
from ai_engine.utils.ffmpeg import ffmpeg_exe
from ai_engine.utils.logging import get_logger

log = get_logger("compose")

# target export resolutions per aspect ratio
_DIMS: dict[AspectRatio, tuple[int, int]] = {
    AspectRatio.WIDE: (1280, 720),
    AspectRatio.VERTICAL: (720, 1280),
    AspectRatio.SQUARE: (1080, 1080),
}


class FFmpegComposer(Composer):
    def __init__(self) -> None:
        self.output_dir = Path.cwd()

    # --- pure command builders (testable) -------------------------------- #
    @staticmethod
    def build_concat_command(list_file: Path, out_path: Path) -> list[str]:
        return [
            ffmpeg_exe(), "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path),
        ]

    @staticmethod
    def build_mux_command(
        video: Path,
        out_path: Path,
        *,
        narration: Optional[Path],
        music: Optional[Path],
        subtitles: Optional[Path],
        dims: tuple[int, int],
    ) -> list[str]:
        w, h = dims
        cmd = [ffmpeg_exe(), "-y", "-i", str(video)]
        if narration:
            cmd += ["-i", str(narration)]
        if music:
            cmd += ["-i", str(music)]

        # letterbox/crop to target aspect without distortion
        vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
        if subtitles:
            # escape path for the subtitles filter
            sub = str(subtitles).replace("\\", "/").replace(":", "\\:")
            vf += f",subtitles='{sub}'"
        cmd += ["-vf", vf]

        # audio mixing: narration at full, music ducked to 0.3
        n_idx, m_idx = 1, (2 if narration else 1)
        if narration and music:
            cmd += ["-filter_complex",
                    f"[{m_idx}:a]volume=0.3[bg];[{n_idx}:a][bg]amix=inputs=2:duration=longest[aout]",
                    "-map", "0:v", "-map", "[aout]"]
        elif narration:
            cmd += ["-map", "0:v", "-map", f"{n_idx}:a"]
        elif music:
            cmd += ["-map", "0:v", "-map", f"{m_idx}:a", "-af", "volume=0.6"]
        else:
            cmd += ["-map", "0:v"]

        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-shortest", str(out_path)]
        return cmd

    @staticmethod
    def build_srt(clips: list[Artifact], narrations: dict[int, str], durations: dict[int, float]) -> str:
        """Build SRT text from per-scene narration + clip durations (cumulative timing)."""
        def ts(sec: float) -> str:
            ms = int((sec - int(sec)) * 1000)
            s = int(sec) % 60
            m = (int(sec) // 60) % 60
            h = int(sec) // 3600
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        lines, t, n = [], 0.0, 1
        for clip in sorted(clips, key=lambda c: c.scene_index or 0):
            idx = clip.scene_index or 0
            dur = durations.get(idx, 4.0)
            text = narrations.get(idx, "").strip()
            if text:
                lines.append(f"{n}\n{ts(t)} --> {ts(t + dur)}\n{text}\n")
                n += 1
            t += dur
        return "\n".join(lines)

    # --- orchestration --------------------------------------------------- #
    def compose(
        self,
        clips: list[Artifact],
        *,
        narration: Optional[list[Artifact]] = None,
        music: Optional[Artifact] = None,
        subtitles: Optional[Artifact] = None,
        aspect_ratio: AspectRatio = AspectRatio.WIDE,
        out_path: Optional[Path] = None,
    ) -> Artifact:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_path or (self.output_dir / "final.mp4")
        ordered = sorted(clips, key=lambda c: c.scene_index or 0)

        # 1) concat clips
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, dir=self.output_dir) as f:
            for c in ordered:
                f.write(f"file '{c.path.as_posix()}'\n")
            list_file = Path(f.name)
        concat_out = self.output_dir / "_concat.mp4"
        subprocess.run(self.build_concat_command(list_file, concat_out), check=True, capture_output=True)

        # 2) single combined narration track (concat of per-scene wavs), if any
        narration_track = self._concat_audio(narration) if narration else None

        # 3) mux video + audio + subtitles, fit aspect ratio
        cmd = self.build_mux_command(
            concat_out, out_path,
            narration=narration_track,
            music=music.path if music else None,
            subtitles=subtitles.path if subtitles else None,
            dims=_DIMS[aspect_ratio],
        )
        subprocess.run(cmd, check=True, capture_output=True)

        list_file.unlink(missing_ok=True)
        log.info("composed final video -> %s (%s)", out_path.name, aspect_ratio.value)
        return Artifact(path=out_path, kind="video", meta={"aspect_ratio": aspect_ratio.value})

    def _concat_audio(self, tracks: list[Artifact]) -> Path:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, dir=self.output_dir) as f:
            for t in sorted(tracks, key=lambda a: a.scene_index or 0):
                f.write(f"file '{t.path.as_posix()}'\n")
            list_file = Path(f.name)
        out = self.output_dir / "_narration.wav"
        subprocess.run(
            [ffmpeg_exe(), "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), str(out)],
            check=True, capture_output=True,
        )
        list_file.unlink(missing_ok=True)
        return out
