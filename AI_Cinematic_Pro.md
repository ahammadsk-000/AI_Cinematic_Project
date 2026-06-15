# 🎬 AI Cinematic Pro (Cineforge) — Complete Project Guide

> Turn a **text script** into a fully **cinematic, narrated, scored MP4 video** — using only **free, open-source AI models** running on **free GPUs** (Google Colab / Kaggle).
> A self-hostable, $0 alternative to RunwayML / Pika / Luma AI.

This document explains the **whole project end-to-end** — what it does, how it's built, the technologies used, how it was deployed online for free, and the issues solved along the way. A new reader can understand the entire system **without reading any code**.

---

## 1. What the project does

You type a short story prompt like:

> *"A young boy walks through a rainy cyberpunk city while cinematic music plays."*

…and the platform automatically produces a finished cinematic video — multiple scenes, AI-generated visuals, motion, a spoken voice-over narration, background music, subtitles, and a downloadable MP4.

**Live example flow:**
1. Register / log in on the website.
2. Open **Generate**, enter a title + story prompt, pick a style (Cinematic Realistic / Anime) and aspect ratio (16:9, 9:16, 1:1).
3. Click **Generate video** → a job is queued.
4. A GPU worker renders it through an 8-stage pipeline (live progress shown on screen).
5. The finished video appears in the **Gallery** — playable in the browser and downloadable as MP4.

---

## 2. The big idea: why it's split into two halves

The hard constraint is **free hosting**: a free CPU server can't run heavy AI models, and free GPUs (Colab/Kaggle) shut down after a few hours. The architecture is designed around that:

| Half | Runs on | Always on? | Job |
|------|---------|-----------|-----|
| **Control plane** (website + API + database + queue) | Free CPU hosts (Vercel + Render + Supabase + Upstash) | ✅ Always on | Accept users, store jobs, show progress, serve videos |
| **GPU worker** (the heavy AI rendering) | Free GPU (Google Colab / Kaggle T4) | ⚡ Ephemeral — start it when you want to render | Pull queued jobs, run the AI models, upload the finished video |

The two halves **never talk directly**. They communicate through a **shared queue (Redis)** and **shared database (Postgres)**:
- The website pushes a job into the queue and forgets about it.
- The GPU worker pulls jobs from the queue whenever it's running.
- If the Colab GPU session dies mid-render, the job simply goes back to the queue and resumes when a worker returns — the website never goes down.

```
        Vercel (website)  ──►  Render (API)  ──►  Supabase (Postgres database)
              ▲                    │
              │ live progress      ├──►  Upstash (Redis: job queue + progress)
              └────────────────────┘                  ▲
                                                       │ pulls jobs (outbound only)
                            Colab / Kaggle GPU worker ─┘
                            (LLM + image + animation + voice + music + compose)
                                         │
                                         └──►  Supabase Storage (final MP4, public)
```

---

## 3. The generation pipeline (8 stages)

Every video is built by an **orchestrator** that runs 8 stages in order. Each stage is independent and checkpointed, so a job that dies halfway resumes from where it stopped.

| # | Stage | What it does | Technology |
|---|-------|--------------|------------|
| 1 | **Scene generation** | Splits your prompt into structured scenes + narration text | **Ollama** (local LLM, e.g. Llama 3) |
| 2 | **Prompt enhancement** | Turns each scene into a rich, cinematic image prompt | Prompt templates |
| 3 | **Image generation** | Renders a still image for each scene | **ComfyUI + SDXL** (Stable Diffusion XL) |
| 4 | **Character lock** | Keeps characters visually consistent across scenes | Reference/identity locking |
| 5 | **Animation** | Turns each still image into a moving clip | **Ken Burns (ffmpeg)** — free, or AnimateDiff/SVD/fal.ai |
| 6 | **Voice** | Generates spoken narration audio | **gTTS** (Google TTS, 50+ languages) or XTTS |
| 7 | **Music** | Creates mood-matched background score | **Library / procedural pad (ffmpeg)** or MusicGen |
| 8 | **Compose** | Stitches clips + narration + music + subtitles into the final MP4 | **FFmpeg** (H.264 video + AAC audio) |

The final video is **H.264 + AAC**, fitted to the chosen aspect ratio, with narration at full volume and music ducked underneath — YouTube / Reels ready.

---

## 4. Technology stack

### Frontend (the website)
- **Next.js 14** (React 18, TypeScript)
- **Tailwind CSS** + **ShadCN UI** components
- **Zustand** (state) + **Framer Motion** (animation)
- Proxies `/api` and `/media` to the backend so the browser stays same-origin
- **Hosted on Vercel** (free Hobby tier)

### Backend / control plane (the brain)
- **FastAPI** (Python) — REST API + live progress over **Server-Sent Events (SSE)**
- **SQLAlchemy 2.0** (async) + **asyncpg** — database access
- **Pydantic / pydantic-settings** — config & validation
- **JWT auth** — `python-jose` + `bcrypt` password hashing
- **Celery** — used **only to enqueue** jobs (it never imports the heavy AI code, keeping the server lightweight)
- **Packaged as a slim Docker image**, **hosted on Render** (free web service)

### AI engine (`packages/ai_engine`)
- A **pure inference layer** with **no web/database dependencies**, so it can be imported and run directly on a Colab GPU.
- Every capability (scene, image, animation, voice, music, compose) is defined behind an **abstract interface** with swappable adapters — changing a model never touches business logic.

### GPU worker (`gpu_worker`)
- A **Celery worker** that runs on the GPU box (Colab/Kaggle/local).
- Boots **ComfyUI** + **Ollama**, pulls jobs from the queue, runs the pipeline, and uploads results.

### Managed free services
| Service | Used for | Free tier |
|---------|----------|-----------|
| **Vercel** | Frontend hosting | Hobby |
| **Render** | Backend (Docker web service) | Free |
| **Supabase** | Postgres database **+ public file storage** | Free |
| **Upstash** | Redis (job queue + live progress) | Free |
| **Google Colab / Kaggle** | GPU worker (T4 GPU) | Free |

---

## 5. How it was deployed online (free, step by step)

Each piece is connected once; afterward every `git push` auto-redeploys the website and backend.

### 5.1 Database — Supabase (Postgres)
1. Create a project at **supabase.com**.
2. Copy the **Transaction pooler** connection string (host contains `pooler.supabase.com`, port `6543`).
   > ⚠️ Use the **pooler**, not the direct `db.<ref>.supabase.co` host — free Render has no IPv6 and can't reach the direct host.
3. Change the scheme to async: `postgresql+asyncpg://postgres.<ref>:<password>@...pooler.supabase.com:6543/postgres`

### 5.2 File storage — Supabase Storage
1. Supabase → **Storage** → create a **public** bucket named **`cineforge`**.
2. Note `SUPABASE_URL` (`https://<ref>.supabase.co`) and the **`service_role`** API key.
   > This is what lets the Colab worker upload the finished MP4 to a public URL the browser can play. Without it, videos render but won't play (the worker and website don't share a disk).

### 5.3 Queue / progress — Upstash (Redis)
1. Create a database at **upstash.com**.
2. Copy the **TLS** URL and build: `rediss://default:<token>@<name>.upstash.io:6379`
   > Use `rediss://` (double-s = TLS). Free Upstash has only DB 0 — the broker, result backend, and progress channel all share one URL.

### 5.4 Backend — Render (FastAPI)
1. Render → **New → Blueprint** → select the GitHub repo. It reads `render.yaml` and creates the **cineforge-api** service.
2. Fill the secret env vars: `DATABASE_URL` (Supabase), `REDIS_URL` (Upstash), `CORS_ORIGINS` (your Vercel URL).
3. Deploy → verify `https://cineforge-api.onrender.com/health` returns `{"status":"ok"}`.
   > Free Render sleeps after ~15 min idle; the first request after a nap takes ~30–60s.

### 5.5 Frontend — Vercel (Next.js)
1. Vercel → **New Project** → import the repo.
2. **Root Directory** = `apps/web`.
3. Env var: `NEXT_PUBLIC_API_URL = https://cineforge-api.onrender.com` → Deploy.
4. Update Render's `CORS_ORIGINS` to your real Vercel URL.

### 5.6 GPU worker — Google Colab
1. Open the worker notebook in Colab (from GitHub or upload `notebooks/colab_gpu_worker.ipynb`).
2. **Runtime → T4 GPU.**
3. In the config cell, paste the **same** Supabase + Upstash URLs, plus `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` (for uploads) and `CINEFORGE_VOICE_LANG="en"`.
4. **Run all** → the worker registers with the queue and renders submitted jobs. Close it to stop using GPU time; reopen to resume.

---

## 6. Key environment variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `DATABASE_URL` | Backend + worker | Supabase Postgres (async, pooled) |
| `REDIS_URL` | Backend + worker | Upstash Redis (queue + progress) — `rediss://…` |
| `CORS_ORIGINS` | Backend | Allowed website origins (your Vercel URL) |
| `SECRET_KEY` | Backend | JWT signing (auto-generated on Render) |
| `NEXT_PUBLIC_API_URL` | Frontend | Backend base URL |
| `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` | Worker | Upload final videos to public storage |
| `CINEFORGE_ANIM_BACKEND` | Worker | `kenburns` (free) / `comfyui` / `svd` / `fal` |
| `CINEFORGE_VOICE_LANG` | Worker | Narration language, e.g. `en` |

---

## 7. Issues solved during deployment (lessons learned)

The deployment surfaced a chain of real-world issues; each was fixed:

| # | Symptom | Root cause | Fix |
|---|---------|-----------|-----|
| 1 | Render container unhealthy | Dockerfile hardcoded port 8000 | Honor Render's injected `$PORT` |
| 2 | Backend crash on boot | `CORS_ORIGINS` parsed as strict JSON | Accept JSON list, CSV, or a bare URL |
| 3 | Crash importing auth | `EmailStr` needs `email-validator` | Add `pydantic[email]` dependency |
| 4 | No Vercel build ever ran | `vercel.json` referenced a non-existent secret | Removed legacy `@secret` env mapping |
| 5 | Registration 500 | Database tables never created (no migrations) | Auto-create schema on startup |
| 6 | DB "Network unreachable" | Used Supabase **direct** host (IPv6); Render has no IPv6 | Switch to Supabase **pooler** (IPv4) |
| 7 | Generate crashed: "No such transport" | `CELERY_BROKER_URL` was blank | Fall back to `REDIS_URL` automatically |
| 8 | Progress stream crashed | Blocking Redis read timed out when idle | Poll with timeout + keep-alive |
| 9 | Video rendered but empty player | Worker & website don't share a disk | Upload final MP4 to **Supabase Storage** |
| 10 | Animation stage failed (401) | `fal.ai` paid backend without a key | Switch to free **Ken Burns** animation |
| 11 | Video had no audio | Scenes had no narration text | Use prompts with explicit narration lines + set voice language |

---

## 8. Repository layout (where things live)

```
AI_Cenimatic_Project/
├── apps/
│   ├── api/          # FastAPI backend (control plane, CPU-only)
│   └── web/          # Next.js website (Vercel)
├── packages/
│   └── ai_engine/    # Pure AI inference layer (runs on Colab) — scene/image/animation/voice/music/compose
├── gpu_worker/       # Celery worker entrypoint for the GPU box
├── comfyui/          # ComfyUI workflow JSON (SDXL, animatediff, etc.)
├── notebooks/        # Colab / Kaggle launch notebooks
├── docker/           # Dockerfiles + local compose
├── render.yaml       # Render deployment blueprint
└── docs/             # ARCHITECTURE / SETUP / API guides
```

---

## 9. Daily usage (after deployment)

- **To make a video:** open the website → Generate → enter a prompt **with narration lines** → Generate.
- **To actually render it:** make sure the **Colab GPU worker is running** (jobs wait in the queue until it is).
- **To ship code changes:** `git push` → Vercel + Render auto-redeploy.
- **To stop GPU costs:** close the Colab tab (everything else stays online for free).

### Tip for good results
Write prompts that **include explicit narration** so the video gets a spoken voice-over, e.g.:
> *"A cinematic film about a lighthouse keeper on a stormy night. Add a calm voice-over narration for each scene: 'On the edge of the world, one light refused to die'…"*

---

## 10. Summary

**AI Cinematic Pro (Cineforge)** is a free, open-source, text-to-cinematic-video platform. It splits an always-on free control plane (Vercel + Render + Supabase + Upstash) from a disposable free GPU worker (Colab/Kaggle) connected by a shared queue and database. An 8-stage AI pipeline turns a text prompt into a narrated, scored, subtitled MP4 using open models (Ollama LLM, SDXL images, gTTS voice, ffmpeg motion/music/compose). The entire thing runs at **$0**, redeploys on every `git push`, and stays online even when the GPU session ends.

🎬 *From a sentence to a finished cinematic film — for free.*
