"""Lightweight logger for the engine. Works identically in a Colab cell and the
GPU worker. No dependency on the backend's logging setup."""

from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False


def setup_engine_logging(level: int | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    lvl = level if level is not None else getattr(logging, os.getenv("CINEFORGE_LOG", "INFO").upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | ai_engine.%(name)s | %(message)s", "%H:%M:%S"))
    logger = logging.getLogger("ai_engine")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(lvl)
    logger.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_engine_logging()
    return logging.getLogger(f"ai_engine.{name}")
