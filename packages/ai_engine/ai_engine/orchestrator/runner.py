"""DefaultOrchestrator — runs the checkpointed stage pipeline.

Responsibilities (docs/ARCHITECTURE.md §5–§7):
  * resume: skip stages already in the manifest;
  * progress: rescale each stage's LOCAL 0-100 into a global band by stage weight,
    so the SSE bar moves smoothly across the whole job;
  * VRAM safety: on VRAMError, shrink resolution/frames and retry the stage before
    failing it;
  * checkpoint after every stage so a killed worker resumes cleanly.
"""

from __future__ import annotations

from ai_engine.interfaces import ProgressReporter
from ai_engine.orchestrator import manifest
from ai_engine.orchestrator.pipeline import JobContext, Orchestrator, Stage, StageStatus
from ai_engine.utils.logging import get_logger
from ai_engine.utils.vram import VRAMError, empty_cache

log = get_logger("orchestrator")


class DefaultOrchestrator(Orchestrator):
    def __init__(self, stages: list[Stage], *, vram_retries: int = 2) -> None:
        self.stages = stages
        self.vram_retries = vram_retries

    def run(self, ctx: JobContext) -> JobContext:
        ctx.workdir.mkdir(parents=True, exist_ok=True)
        data = manifest.load(ctx.workdir)
        ctx.completed_stages = set(data.get("completed", []))
        total_weight = sum(s.weight for s in self.stages) or 1.0
        raw_report = ctx.report

        done_weight = sum(s.weight for s in self.stages if s.name in ctx.completed_stages)

        for stage in self.stages:
            band_start = done_weight / total_weight * 100
            band_size = stage.weight / total_weight * 100

            # wrap the reporter so stages emit LOCAL 0-100 and we publish GLOBAL pct
            ctx.report = self._scaled_reporter(raw_report, band_start, band_size)

            if stage.already_done(ctx):
                log.info("skip %s (already complete)", stage.name)
                done_weight += stage.weight
                continue

            log.info("→ stage %s", stage.name)
            result = self._run_stage(stage, ctx)
            if result.status == StageStatus.FAILED:
                if raw_report:
                    raw_report(stage=stage.name, pct=band_start, message=result.error or "stage failed")
                raise RuntimeError(f"stage '{stage.name}' failed: {result.error}")

            ctx.artifacts.setdefault(stage.name, result.artifacts)
            ctx.completed_stages.add(stage.name)
            manifest.mark_complete(ctx.workdir, stage.name, [str(a.path) for a in result.artifacts])
            done_weight += stage.weight
            empty_cache()  # free VRAM between heavy stages

        ctx.report = raw_report
        if raw_report:
            raw_report(stage="compose", pct=100.0, message="completed")
        return ctx

    # --- helpers ---------------------------------------------------------- #
    @staticmethod
    def _scaled_reporter(raw: ProgressReporter | None, band_start: float, band_size: float):
        def report(*, stage: str, pct: float, message: str = "", **extra) -> None:
            if raw is None:
                return
            global_pct = band_start + (max(0.0, min(100.0, pct)) / 100.0) * band_size
            raw(stage=stage, pct=round(global_pct, 1), message=message, **extra)

        return report

    def _run_stage(self, stage: Stage, ctx: JobContext):
        attempt = 0
        while True:
            try:
                return stage.run(ctx)
            except VRAMError as exc:
                attempt += 1
                if attempt > self.vram_retries:
                    log.error("%s OOM after %d retries", stage.name, self.vram_retries)
                    from ai_engine.orchestrator.pipeline import StageResult

                    return StageResult(stage.name, StageStatus.FAILED, error=f"VRAM OOM: {exc}")
                self._shrink(ctx)
                empty_cache()
                log.warning("%s OOM — retry %d at %dx%d, %d frames",
                            stage.name, attempt, ctx.config.width, ctx.config.height, ctx.config.frames_per_clip)

    @staticmethod
    def _shrink(ctx: JobContext) -> None:
        """Reduce the generation footprint before a VRAM retry."""
        ctx.config.width = max(512, int(ctx.config.width * 0.8))
        ctx.config.height = max(288, int(ctx.config.height * 0.8))
        ctx.config.frames_per_clip = max(8, int(ctx.config.frames_per_clip * 0.75))
        ctx.config.steps = max(18, int(ctx.config.steps * 0.85))
