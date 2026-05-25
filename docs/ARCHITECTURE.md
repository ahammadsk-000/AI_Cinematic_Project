# Cineforge — Architecture

This document is the source of truth for *why* the system is shaped the way it is. Code in later phases must conform to the contracts described here.

---

## 1. The core constraint

We must run on **free** infrastructure simultaneously:

- **Free CPU host** (Render / Railway free tier) — always-on, but **no GPU** and goes to sleep on inactivity.
- **Free GPU** (Google Colab / Kaggle) — strong GPU (T4 ~16 GB), but **ephemeral**: sessions are killed after a few hours / on idle, and have no stable inbound address.
- **Optional local GPU** (RTX 3060, 12 GB) — stable but not always on.

No single machine satisfies "always-on + has-a-GPU + free." Therefore the system is **split**, and the GPU side is treated as **disposable and replaceable**.

---

## 2. Topology — Split control plane / GPU worker

```
                         ┌───────────────────────── CONTROL PLANE (free CPU, always-on) ─────────────────────────┐
   Browser ── HTTPS ──►  │  Next.js (Vercel)  ──►  FastAPI (Render)  ──►  PostgreSQL (Supabase)                   │
        ▲                │                              │                                                          │
        │  SSE progress  │                              ├──►  Redis (queue + job state + pub/sub progress)         │
        └────────────────┤                              │                                                          │
                         └──────────────────────────────┼──────────────────────────────────────────────────────┘
                                                         │  jobs pushed onto Redis queue
                                                         ▼
                         ┌───────────────────── GPU WORKER (ephemeral: Colab / Kaggle / local) ──────────────────┐
                         │  Celery worker  ──►  ai_engine.orchestrator  ──►  ComfyUI server (localhost:8188)       │
                         │       │                                              │                                  │
                         │       │  publishes stage progress back to Redis      │  SDXL · ControlNet · IPAdapter   │
                         │       ▼                                              │  AnimateDiff · SVD               │
                         │  artifacts written to storage (local FS or S3/Supabase Storage)                        │
                         └──────────────────────────────────────────────────────────────────────────────────────┘
```

**Key properties**

- The control plane **never imports** `ai_engine` heavy deps (torch, diffusers). It only *enqueues* jobs and *reads* progress/results. This keeps the Render image tiny and CPU-only.
- The GPU worker **pulls** from Redis — no inbound connection to the GPU box is required. (A `cloudflared`/`ngrok` tunnel is only needed if we want to expose the ComfyUI UI for debugging; it is **not** on the critical path.)
- Job state lives in Postgres (durable) + Redis (hot). If a Colab session dies, the in-flight job's Celery task is re-queued (`acks_late=True`), and resumes from its last checkpoint.

---

## 3. Layering (Clean Architecture)

```
   ┌─────────────────────────────────────────────────────────────┐
   │  API layer        apps/api/app/api/v1     (HTTP, SSE, auth)   │  ← thin; no business logic
   ├─────────────────────────────────────────────────────────────┤
   │  Service layer    apps/api/app/services   (use-cases)         │  ← orchestrates repos + enqueues tasks
   ├─────────────────────────────────────────────────────────────┤
   │  Repository layer apps/api/app/repositories (data access)     │  ← only place that touches the ORM
   ├─────────────────────────────────────────────────────────────┤
   │  Domain models    apps/api/app/models / schemas               │  ← ORM + Pydantic
   └─────────────────────────────────────────────────────────────┘

   ┌─────────────────────────────────────────────────────────────┐
   │  ai_engine (separate package, GPU side)                       │
   │    interfaces.py  → abstract backends (the contract)          │
   │    backends/      → concrete adapters (comfyui, ollama, ...)  │
   │    <stage>/       → stage logic built on the interfaces       │
   │    orchestrator/  → wires stages into the pipeline            │
   └─────────────────────────────────────────────────────────────┘
```

**Hard rules**
1. Endpoints call **services**, never repositories or the ORM directly.
2. Only **repositories** touch SQLAlchemy. Services receive/return Pydantic schemas or domain objects.
3. `ai_engine` has **zero** dependency on FastAPI, SQLAlchemy, or Celery. It is a pure library — importable standalone inside a Colab cell. The Celery task in `gpu_worker` is the *only* glue between the queue and `ai_engine`.
4. Adding a new model = new adapter in `backends/` implementing an existing interface. **No call site changes.** This is the "never break existing functionality" guarantee, enforced structurally.

---

## 4. The inference abstraction (`ai_engine/interfaces.py`)

Every capability is an abstract base class. Concrete models are adapters selected by config.

| Interface | Responsibility | Default adapter | Alt adapters |
|-----------|----------------|-----------------|--------------|
| `SceneBackend` | script → structured `Scene[]` | `OllamaSceneBackend` (Llama3/Mistral/Qwen) | OpenAI-compatible |
| `ImageBackend` | prompt (+ control/ref) → image | `ComfyUIImageBackend` (SDXL) | `DiffusersImageBackend` |
| `CharacterEngine` | lock identity across scenes | IPAdapter + face-embed + LoRA | ControlNet reference |
| `AnimationBackend` | image(s) → video clip | `ComfyUIAnimateDiffBackend` | `SVDBackend`, `DiffusersSVD` |
| `VoiceBackend` | text → narration audio | `XTTSBackend` | `BarkBackend`, `CoquiBackend` |
| `MusicBackend` | mood → score audio | `MusicGenBackend` | AudioCraft variants |
| `Composer` | clips+audio+subs → MP4 | `FFmpegComposer` | `MoviePyComposer` |

All backends share a common lifecycle: `load()` / `unload()` / `is_loaded` so the orchestrator can **load one model, run it, free VRAM, load the next** — the central low-VRAM strategy (see §6).

---

## 5. The pipeline (`ai_engine/orchestrator`)

A job is a list of **stages**. Each stage:
- declares its inputs (artifacts from prior stages) and outputs,
- is **idempotent** and **checkpointed** (writes a manifest entry on completion),
- publishes a progress event (`stage`, `pct`, `message`) to Redis for SSE.

```
PIPELINE = [SceneGen, PromptEnhance, ImageGen, CharacterLock,
            Animate, Voice, Music, Compose]
```

On resume, the orchestrator reads the job manifest and skips already-completed stages. A crash in `Animate` never re-bills `SceneGen`/`ImageGen`.

---

## 6. Low-VRAM strategy (T4 16 GB / RTX 3060 12 GB)

This is a first-class architectural concern, not an afterthought:

1. **One heavy model resident at a time.** The orchestrator runs stages sequentially and calls `unload()` between heavy stages; ComfyUI's own model management handles intra-stage offload.
2. **fp16 everywhere**, plus optional 8-bit/4-bit for the LLM (via Ollama quant) and sequential CPU offload for diffusion when VRAM is tight.
3. **VAE tiling + attention slicing** for SDXL at high res; generate at 768–1024 then upscale.
4. **Short animation windows** (16–24 frames) per clip, stitched in compose — never animate the whole video at once.
5. **Graceful OOM handling:** a `VRAMError` triggers an automatic retry with reduced resolution/frames/batch before failing the stage.
6. **Model cache** lives under `storage/models` (or HF cache) and is reused across sessions/jobs.

---

## 7. Job lifecycle & recovery

```
PENDING → QUEUED → RUNNING(stage=…, pct=…) → COMPLETED
                              │
                              ├── retryable error → QUEUED (re-pull, resume from checkpoint)
                              └── fatal error     → FAILED (with stage + traceback)
```

- Celery `task_acks_late=True` + `worker_prefetch_multiplier=1` so a killed Colab worker returns the job to the queue.
- Progress is written to both Postgres (durable, for refresh/history) and Redis pub/sub (live SSE stream).
- A reaper marks jobs `RUNNING` with no heartbeat for N minutes back to `QUEUED`.

---

## 8. Configuration

- **Backend** config: pydantic-settings, env-driven (`apps/api/app/core/config.py`).
- **ai_engine** config: a plain dataclass/`pydantic` settings object (`ai_engine/config.py`) with **no** web deps, so it works identically in a Colab cell and in the worker.
- Model selection, VRAM budget, resolution presets, and adapter choices are all config — never hardcoded at call sites.

---

## 9. Storage abstraction

`storage/` is the local default. A `StorageBackend` interface (Phase 4/6) allows swapping to Supabase Storage / S3 without touching pipeline code. Artifacts are addressed by `job_id/stage/filename`.
