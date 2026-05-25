"""Tests for the library/procedural music backend (pure command + mood logic)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "ai_engine"))

from ai_engine.music.library_backend import LibraryMusicBackend  # noqa: E402


def test_mood_to_chord():
    b = LibraryMusicBackend()
    assert b._chord_for("soft emotional warm") == [130.81, 164.81, 196.00]   # major/warm
    assert b._chord_for("suspenseful, tense") == [65.41, 92.50]              # dark/tritone
    assert b._chord_for("nonsense mood") == [130.81, 196.00, 261.63]         # default


def test_procedural_command_is_valid():
    b = LibraryMusicBackend()
    cmd = b.build_procedural_command([130.81, 164.81, 196.0], 6.0, Path("score.wav"))
    joined = " ".join(cmd)
    assert "amix=inputs=3" in joined        # all 3 tones mixed
    assert "sine=frequency=130.81" in joined
    assert "tremolo" in joined and "lowpass" in joined and "afade" in joined
    assert cmd[-1] == "score.wav"


def test_loop_command_for_supplied_track():
    b = LibraryMusicBackend()
    cmd = b.build_loop_command(Path("emotional.mp3"), Path("out.wav"), 12.0)
    joined = " ".join(cmd)
    assert "-stream_loop" in cmd and "-1" in cmd     # loop to fill duration
    assert "-t 12.00" in joined
    assert "afade" in joined


def test_find_track_by_mood(tmp_path):
    (tmp_path / "emotional.mp3").write_bytes(b"x")
    (tmp_path / "action.wav").write_bytes(b"x")
    b = LibraryMusicBackend(music_dir=tmp_path)
    assert b._find_track("soft emotional scene").name == "emotional.mp3"
    assert b._find_track("epic action").name == "action.wav"
    assert b._find_track("unknown").suffix in {".mp3", ".wav"}   # falls back to first track


def test_no_music_dir_returns_none():
    assert LibraryMusicBackend(music_dir=None)._find_track("emotional") is None
