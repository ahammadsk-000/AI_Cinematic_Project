# GPU Worker

The disposable muscle. Runs **wherever a free GPU is** — Google Colab, Kaggle, or
a local RTX 3060 — and **pulls** video-generation jobs from the Redis queue. No
inbound connection to this box is required, so it works fine behind Colab/Kaggle
NAT with no public address.

```
Redis queue ──pull──► Celery worker ──► ai_engine.orchestrator ──► ComfyUI (localhost:8188)
                          │                                            SDXL · ControlNet · IPAdapter
                          └── publishes stage progress back to Redis    AnimateDiff · SVD
```

## What lives here (filled in Phase 4–5)

- `worker.py` — Celery app configured against the shared broker; `task_acks_late=True`
  and `prefetch_multiplier=1` so a killed Colab session re-queues the job.
- `tasks.py` — the single `generate_video(job_id)` task: loads `JobContext`, runs the
  orchestrator, streams progress to Redis, writes artifacts to storage.
- `bootstrap.py` — boots a local ComfyUI server + downloads required models on first run.
- `requirements.txt` — heavy GPU deps (torch, diffusers, transformers, TTS, audiocraft).

## Why a separate package from `apps/api`

`apps/api` is CPU-only and must stay deployable on a free 512 MB Render instance.
This worker is the *only* component that imports `ai_engine`'s GPU extras. The two
share nothing but the Redis broker URL and the storage location.

## Running (Phase 6 will provide the Colab/Kaggle notebooks that wrap this)

```bash
pip install -r gpu_worker/requirements.txt
pip install -e packages/ai_engine[gpu]
export CELERY_BROKER_URL=redis://<your-redis>:6379/1
export COMFYUI_URL=http://127.0.0.1:8188
python -m gpu_worker            # boots ComfyUI + starts pulling jobs
```
