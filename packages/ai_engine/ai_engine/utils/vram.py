"""VRAM helpers + the VRAMError the orchestrator catches to trigger a reduced-
resolution retry (docs/ARCHITECTURE.md §6). All torch access is lazy so importing
this module on a CPU-only box (or in a unit test) never fails."""

from __future__ import annotations

from ai_engine.utils.logging import get_logger

log = get_logger("vram")


class VRAMError(RuntimeError):
    """Raised on CUDA OOM. The orchestrator catches this and retries the stage
    with a smaller resolution / fewer frames before failing it."""


def _torch():
    try:
        import torch  # noqa: PLC0415 - lazy by design

        return torch
    except ImportError:
        return None


def cuda_available() -> bool:
    t = _torch()
    return bool(t and t.cuda.is_available())


def free_vram_gb() -> float:
    """Best-effort free VRAM in GB. Returns 0.0 when CUDA isn't present."""
    t = _torch()
    if not (t and t.cuda.is_available()):
        return 0.0
    free, _total = t.cuda.mem_get_info()
    return free / (1024**3)


def empty_cache() -> None:
    """Free cached allocations after unloading a model (the core low-VRAM lever)."""
    t = _torch()
    if t and t.cuda.is_available():
        t.cuda.empty_cache()
        t.cuda.ipc_collect()
        log.debug("cuda cache emptied; %.2f GB free", free_vram_gb())


def is_oom(exc: BaseException) -> bool:
    """Heuristically detect a CUDA out-of-memory error from any exception."""
    msg = str(exc).lower()
    return "out of memory" in msg or "cuda oom" in msg or "alloc" in msg and "fail" in msg
