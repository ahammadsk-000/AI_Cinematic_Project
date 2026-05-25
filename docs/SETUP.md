# Cineforge — Setup & Deployment Guide

End-to-end instructions to run Cineforge **100% free**: local development first, then
a fully free-tier production deployment (Vercel + Render + Supabase + Upstash + Colab/Kaggle GPU).

---

## 0. How the pieces fit

```
        Vercel (Next.js)  ──►  Render (FastAPI)  ──►  Supabase (Postgres)
              ▲                      │
              │ SSE                  ├──►  Upstash (Redis: queue + progress)
              └──────────────────────┘                  ▲
                                                         │ pulls jobs (outbound only)
                              Colab / Kaggle / local GPU ─┘
                              (Ollama + ComfyUI + Celery worker)
```

The control plane (top row) is always-on and CPU-only. The GPU worker is **ephemeral** —
start it on a free Colab/Kaggle session whenever you want to render; jobs queued while no
worker is running simply wait, and a worker that dies re-queues its in-flight job.

---

## 1. Local development (everything on your machine)

**Prerequisites:** Docker Desktop, Node 18+, Python 3.11+. A local NVIDIA GPU is optional —
without one, set `CINEFORGE_ANIM_BACKEND=kenburns` and the pipeline still produces video
(it just won't run AnimateDiff/SVD).

### 1.1 Start the control plane

```bash
cp .env.example .env
# edit .env: set SECRET_KEY (openssl rand -hex 32). Defaults point at the compose services.
docker compose up -d postgres redis        # databases only
```

### 1.2 Run the backend

```bash
cd apps/api
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# health check: http://localhost:8000/health   ·   docs: http://localhost:8000/docs
```

### 1.3 Run the frontend

```bash
cd apps/web
cp .env.local.example .env.local            # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                                  # http://localhost:3000
```

Register an account, open **Generate**, submit a script. The job will sit in `queued`
until you start a worker.

### 1.4 Run the GPU worker locally

Install Ollama (https://ollama.com) and pull a model: `ollama pull llama3`.
Optionally run a local ComfyUI on `:8188` (or use `kenburns` to skip it).

```bash
# from repo root, in a venv with the GPU extras
pip install -r gpu_worker/requirements.txt
pip install -e packages/ai_engine
# share the schema + connect to local infra
export PYTHONPATH="$PWD:$PWD/apps/api:$PWD/packages/ai_engine"
export DATABASE_URL="postgresql+asyncpg://cineforge:cineforge@localhost:5432/cineforge"
export CELERY_BROKER_URL="redis://localhost:6379/1"
export REDIS_URL="redis://localhost:6379/0"
export CINEFORGE_ANIM_BACKEND=kenburns      # or comfyui if you run a local ComfyUI
python -m gpu_worker
```

Watch the job move through the 8 stages live in the UI.

---

## 2. Free-tier production deployment

### 2.1 Postgres — Supabase (free)
1. Create a project at https://supabase.com.
2. **Project Settings → Database → Connection string → URI**. Use the **pooled** (port 6543)
   string for the backend.
3. Convert it to the async driver Cineforge expects:
   `postgresql+asyncpg://postgres.<ref>:<pw>@<host>:6543/postgres`
   (The worker auto-converts this to a sync URL internally.)

### 2.2 Redis — Upstash (free)
1. Create a database at https://upstash.com (pick a region near your Render region).
2. Copy the `rediss://...` URL. You'll use three logical DBs by changing the trailing number:
   `/0` (progress pub/sub), `/1` (Celery broker), `/2` (results).

### 2.3 Backend — Render (free)
1. Push the repo to GitHub.
2. Render → **New → Blueprint**, select the repo. It reads [`render.yaml`](../render.yaml).
3. Fill the `sync: false` secrets: `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`,
   `CELERY_RESULT_BACKEND`, `CORS_ORIGINS` (your Vercel URL as a JSON list).
4. Deploy. Verify `https://<your-api>.onrender.com/health`.
   > Free Render instances sleep after inactivity; the first request after idle is slow.

### 2.4 Frontend — Vercel (free)
1. Vercel → **New Project** → import the repo.
2. **Root Directory: `apps/web`** (monorepo).
3. Add env var `NEXT_PUBLIC_API_URL = https://<your-api>.onrender.com`.
4. Deploy. The Next rewrites proxy `/api/*` and `/media/*` to the backend.
5. Update Render's `CORS_ORIGINS` to include the Vercel URL and redeploy.

### 2.5 GPU worker — Colab or Kaggle
- **Colab:** open [`notebooks/colab_gpu_worker.ipynb`](../notebooks/colab_gpu_worker.ipynb),
  set runtime to **T4 GPU**, fill the config cell with your Supabase + Upstash URLs, run all cells.
- **Kaggle:** open [`notebooks/kaggle_gpu_worker.ipynb`](../notebooks/kaggle_gpu_worker.ipynb),
  enable **GPU + Internet**, store secrets, run all cells.

The worker registers with the queue and starts rendering submitted jobs. Close the notebook
to stop paying GPU time; restart it later — queued jobs resume.

---

## 3. Environment variable reference

| Variable | Where | Purpose |
|----------|-------|---------|
| `SECRET_KEY` | backend | JWT signing key (`openssl rand -hex 32`) |
| `DATABASE_URL` | backend + worker | `postgresql+asyncpg://…` (worker converts to sync) |
| `REDIS_URL` | backend + worker | progress pub/sub (`…/0`) |
| `CELERY_BROKER_URL` | backend + worker | job queue (`…/1`) |
| `CELERY_RESULT_BACKEND` | backend + worker | task results (`…/2`) |
| `CORS_ORIGINS` | backend | JSON list of allowed frontend origins |
| `NEXT_PUBLIC_API_URL` | frontend | backend base URL |
| `OLLAMA_HOST` | worker | local Ollama (`http://127.0.0.1:11434`) |
| `COMFYUI_URL` | worker | local ComfyUI (`http://127.0.0.1:8188`) |
| `CINEFORGE_LLM_MODEL` | worker | `llama3` / `mistral` / `qwen2` |
| `CINEFORGE_ANIM_BACKEND` | worker | `comfyui` (AnimateDiff) or `kenburns` (no-GPU) |
| `CINEFORGE_VRAM_GB` | worker | VRAM budget hint (15 for T4, 11 for RTX 3060) |

See [`.env.example`](../.env.example) for the full list.

---

## 4. GPU optimization & low-VRAM tricks

These are built in and tunable via env (docs/ARCHITECTURE.md §6):

- **One heavy model resident at a time** — the orchestrator `load()`s a backend, runs the
  stage, `unload()`s it (ComfyUI `/free`) before the next. This is the single biggest win.
- **fp16 + sequential CPU offload + VAE tiling/slicing** (`CINEFORGE_FP16/CPU_OFFLOAD/VAE_TILING`).
- **Short animation windows** (`frames_per_clip`, default 16) — never animate the whole video at once.
- **Automatic OOM recovery** — a CUDA OOM raises `VRAMError`; the orchestrator shrinks
  resolution/frames/steps and retries before failing the stage.
- **Ken Burns fallback** — `CINEFORGE_ANIM_BACKEND=kenburns` produces cinematic motion via
  ffmpeg with **zero VRAM**, so even a tiny GPU (or none) finishes a video.
- **Smaller models** — MusicGen defaults to `small`; ComfyUI launched with `--lowvram`.

**Recommended free models:** SDXL base 1.0 (image), `mm_sd_v15_v2` motion module (AnimateDiff),
Llama 3 / Mistral / Qwen2 via Ollama (scenes), XTTS v2 (voice), MusicGen-small (music).

---

## 5. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Job stuck in `queued` | No worker running — start a Colab/Kaggle session. |
| `connection refused` to Redis from Colab | Use the `rediss://` (TLS) Upstash URL, not `redis://`. |
| Worker can't import `app.models` | Ensure `apps/api` is on `PYTHONPATH` (notebooks do this). |
| ComfyUI animation fails | Install the AnimateDiff-Evolved + VideoHelperSuite custom nodes (notebooks do this), or switch to `kenburns`. |
| CUDA OOM repeatedly | Lower `CINEFORGE_VRAM_GB`, set `kenburns`, or reduce scene count. |
| Video won't play in UI | Confirm `/media/*` rewrite reaches the backend and the file exists under `storage/outputs/<job_id>/`. |
| First request to API very slow | Free Render instance was asleep; it spins up on demand. |
