# 🎬 Cineforge — Free & Open-Source Cinematic AI Video Platform

> Turn a text script into a cinematic, narrated, scored MP4 — using **only free, open-source models** running on **free GPUs** (Google Colab / Kaggle) or a local RTX 3060.

A self-hostable, free alternative to RunwayML / Pika / Luma AI / PixVerse.

```
"A young boy walks through a rainy cyberpunk city while cinematic music plays."
        │
        ▼   Script → Scenes → Prompts → Images → Character-locked → Animation → Voice → Music → Compose
        ▼
   final_cinematic_video.mp4   (16:9 / 9:16 / 1:1 · subtitles · transitions · scored · narrated)
```

---

## Why this architecture

The hard constraint — **free CPU backend (Render/Railway) + free GPU (Colab/Kaggle, which die after a few hours)** — drives every decision:

- **Split topology.** The always-on brain (API, DB, queue, job state) runs on a free CPU host. The disposable muscle (GPU worker running the heavy diffusion/animation models) runs wherever a free GPU is available and **pulls jobs from the queue**. When a Colab session dies, jobs simply re-queue — the platform stays up.
- **ComfyUI as the generation engine.** ComfyUI's smart model-offloading is the single most important lever for fitting SDXL + ControlNet + IPAdapter + AnimateDiff into ~12–16 GB VRAM. The engine talks to it over its HTTP/WebSocket API using reusable workflow JSON files.
- **Everything behind an interface.** Scene generation, image, animation, voice, music, and composition are each defined as an abstract backend. ComfyUI / Diffusers / Ollama / XTTS / MusicGen are *adapters*. Swapping a model never touches business logic.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design.

---

## Monorepo layout

```
AI_Cenimatic_Project/
├── apps/
│   ├── api/                  # FastAPI backend — auth, jobs, REST, SSE progress (CPU-only)
│   │   └── app/
│   │       ├── core/         #   config, logging, security
│   │       ├── api/v1/        #   REST + SSE endpoints
│   │       ├── models/       #   SQLAlchemy ORM
│   │       ├── schemas/      #   Pydantic request/response
│   │       ├── repositories/ #   data-access layer
│   │       ├── services/     #   business logic
│   │       ├── tasks/        #   Celery task definitions (enqueue only)
│   │       └── db/           #   session / migrations
│   └── web/                  # Next.js 14 + TS + Tailwind + ShadCN + Zustand + Framer Motion
│
├── packages/
│   └── ai_engine/            # ★ Pure inference layer — NO web/db deps. Importable on Colab.
│       └── ai_engine/
│           ├── interfaces.py #   abstract backends (the contract)
│           ├── backends/     #   concrete adapters (comfyui, diffusers, ollama, xtts, musicgen)
│           ├── scene/        #   script → structured scenes (LLM)
│           ├── image/        #   cinematic image generation
│           ├── character/    #   consistency engine (face embed, IPAdapter, LoRA, ref-lock)
│           ├── animation/    #   AnimateDiff / SVD + camera moves
│           ├── voice/        #   XTTS v2 / Bark narration
│           ├── music/        #   MusicGen scoring
│           ├── compose/      #   FFmpeg / MoviePy stitching + subtitles + transitions
│           └── orchestrator/ #   the 9-stage pipeline that wires it all together
│
├── gpu_worker/               # Celery worker entrypoint that runs on the GPU box (Colab/Kaggle/local)
├── comfyui/workflows/        # reusable ComfyUI workflow JSON (txt2img, ctrlnet, ipadapter, animatediff, svd)
├── notebooks/                # Colab + Kaggle launch notebooks (boot ComfyUI + tunnel + worker)
├── prompts/                  # cinematic prompt-engineering templates & presets
├── docker/                   # Dockerfiles + compose for local-first deployment
├── storage/                  # local artifact store (uploads, outputs, model cache)  [gitignored]
├── scripts/                  # setup / model-download / smoke-test scripts
├── docs/                     # ARCHITECTURE.md, API docs, setup guides
└── tests/
```

---

## The generation pipeline

```
                ┌──────────────────────────── ai_engine.orchestrator ─────────────────────────────┐
  script  ──►   │  1 SceneGen   2 PromptEnhance   3 ImageGen   4 CharacterLock   5 Animate         │
                │       (LLM/Ollama)        (templates)     (ComfyUI SDXL)   (IPAdapter/LoRA)  (AnimateDiff/SVD)  │
                │                                                                                  │
                │  6 Voice      7 Music         8 Compose                                          │
                │   (XTTS/Bark)  (MusicGen)      (FFmpeg/MoviePy → MP4)                            │
                └──────────────────────────────────────────────────────────────────────────────────┘
```

Each stage is idempotent and checkpointed, so a job that dies mid-pipeline (GPU session lost) resumes from the last completed stage instead of restarting.

---

## Status

| Phase | Scope | State |
|-------|-------|-------|
| **1** | Architecture + folder structure + core abstractions | ✅ |
| **2** | Backend (FastAPI, auth, jobs, repositories, services, SSE) | ✅ |
| **3** | Frontend (Next.js cinematic UI) | ✅ |
| **4** | AI pipeline (scene/prompt/image/character backends) | ✅ |
| **5** | Video pipeline (animation/voice/music/compose + GPU worker) | ✅ |
| **6** | Deployment (Vercel + Render + Supabase + Colab/Kaggle notebooks) | ✅ |
| **7** | Optimization + scaling (GPU-tier auto-tune, heartbeat reaper, queue dashboard) | ✅ |

**All 7 phases complete.** 22 tests passing across backend + AI engine + pipeline; frontend `next build` green. See [docs/SETUP.md](docs/SETUP.md) to run it and [docs/API.md](docs/API.md) for the API.

---

## Quickstart (local-first, once Phase 2+ lands)

```bash
cp .env.example .env          # fill in secrets
docker compose up -d          # postgres + redis + api + web
# on the GPU box (local or Colab):
python -m gpu_worker          # boots ComfyUI, registers with the queue, pulls jobs
```

Full setup — including the Colab/Kaggle notebooks and tunnel wiring — lands in Phase 6 (`docs/SETUP.md`).

## License

Open-source (MIT). All bundled models are free/open-weight; check each model's individual license before commercial use.
