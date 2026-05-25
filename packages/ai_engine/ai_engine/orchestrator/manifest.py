"""Job manifest — the checkpoint that makes the pipeline resumable.

After each stage completes, the orchestrator appends it (and its artifact paths)
to <workdir>/manifest.json. On a re-run (e.g. after a Colab session died), the
orchestrator reads this and skips completed stages — a crash in `animation` never
re-runs `scene_generation`/`image_generation` (docs/ARCHITECTURE.md §7)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_MANIFEST = "manifest.json"


def load(workdir: Path) -> dict[str, Any]:
    path = workdir / _MANIFEST
    if path.exists():
        try:
            return json.loads(path.read_text("utf-8"))
        except json.JSONDecodeError:
            pass
    return {"completed": [], "artifacts": {}}


def save(workdir: Path, data: dict[str, Any]) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / _MANIFEST).write_text(json.dumps(data, indent=2, default=str), "utf-8")


def mark_complete(workdir: Path, stage: str, artifact_paths: list[str]) -> dict[str, Any]:
    data = load(workdir)
    if stage not in data["completed"]:
        data["completed"].append(stage)
    data["artifacts"][stage] = artifact_paths
    save(workdir, data)
    return data
