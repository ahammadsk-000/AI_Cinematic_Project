"""Generic retry with exponential backoff. Used for flaky network calls to
Ollama / ComfyUI and for VRAM-pressure retries (handled separately in the
orchestrator, which reduces resolution between attempts)."""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import TypeVar

from ai_engine.utils.logging import get_logger

log = get_logger("retry")
T = TypeVar("T")


def retry(
    attempts: int = 3,
    backoff: float = 1.0,
    factor: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
):
    """Retry the wrapped callable up to ``attempts`` times with exponential backoff."""

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            delay = backoff
            last: BaseException | None = None
            for i in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:  # noqa: BLE001 - intentional broad catch, re-raised below
                    last = exc
                    if i == attempts:
                        break
                    log.warning("%s failed (attempt %d/%d): %s — retrying in %.1fs", fn.__name__, i, attempts, exc, delay)
                    time.sleep(delay)
                    delay *= factor
            assert last is not None
            raise last

        return wrapper

    return decorator
