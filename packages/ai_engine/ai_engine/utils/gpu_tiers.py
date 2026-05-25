"""GPU-tier auto-tuning.

Detects the available VRAM and returns a preset that clamps resolution, frame
count, sampling steps, model sizes, and offload flags so a job is sized to the
hardware *before* it OOMs — complementing the orchestrator's reactive VRAMError
retry (docs/ARCHITECTURE.md §6). Pure and fully testable: VRAM detection is the
only impure call and it's injectable.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_engine.utils.logging import get_logger
from ai_engine.utils.vram import cuda_available, free_vram_gb

log = get_logger("gpu_tiers")


@dataclass(frozen=True)
class TierPreset:
    name: str
    width: int
    height: int           # for 16:9; other ratios scale from this longest edge
    frames_per_clip: int
    steps: int
    musicgen_size: str
    enable_cpu_offload: bool
    # force the no-GPU animation path when a motion model won't fit
    force_kenburns: bool


# Ordered worst → best. A tier is chosen by the largest one whose budget fits.
TIERS: dict[str, TierPreset] = {
    "cpu": TierPreset("cpu", 512, 288, 8, 18, "small", True, True),
    "low": TierPreset("low", 768, 432, 12, 22, "small", True, True),   # ≤8 GB (RTX 3050/3060 6-8GB)
    "t4": TierPreset("t4", 1024, 576, 16, 28, "small", True, False),   # ~12-16 GB (T4 / RTX 3060 12GB)
    "high": TierPreset("high", 1152, 648, 24, 32, "medium", False, False),  # >16 GB (A10/A100/3090+)
}


def detect_tier(vram_gb: float | None = None) -> TierPreset:
    """Pick a tier from available VRAM. Pass vram_gb to override detection (tests)."""
    if vram_gb is None:
        vram_gb = free_vram_gb() if cuda_available() else 0.0
    if vram_gb < 2:
        tier = TIERS["cpu"]
    elif vram_gb <= 8:
        tier = TIERS["low"]
    elif vram_gb <= 16:
        tier = TIERS["t4"]
    else:
        tier = TIERS["high"]
    log.info("GPU tier: %s (%.1f GB available)", tier.name, vram_gb)
    return tier


def apply_tier(gen_cfg, tier: TierPreset) -> None:
    """Clamp a GenerationConfig down to the tier (never up — respect explicit lower
    requests). Mutates in place. The aspect-ratio's own dims still win on the
    short edge; this caps the long edge + footprint."""
    longest = max(gen_cfg.width, gen_cfg.height)
    if longest > tier.width:
        scale = tier.width / longest
        gen_cfg.width = (int(gen_cfg.width * scale) // 8) * 8
        gen_cfg.height = (int(gen_cfg.height * scale) // 8) * 8
    gen_cfg.frames_per_clip = min(gen_cfg.frames_per_clip, tier.frames_per_clip)
    gen_cfg.steps = min(gen_cfg.steps, tier.steps)
