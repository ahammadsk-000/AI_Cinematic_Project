# Local GPU worker image. Use ONLY if you have a local NVIDIA GPU; Colab/Kaggle
# use the notebooks instead. Built from the repo root.
#
#   docker build -f docker/worker.Dockerfile -t cineforge-worker .
#   docker run --gpus all --env-file .env cineforge-worker
#
# Requires the NVIDIA Container Toolkit on the host.
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV PYTHONUNBUFFERED=1 DEBIAN_FRONTEND=noninteractive \
    PYTHONPATH=/app:/app/apps/api:/app/packages/ai_engine

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3-pip git ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch matching the CUDA base, then the rest of the worker deps
RUN pip3 install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu121
COPY gpu_worker/requirements.txt ./gpu_worker/requirements.txt
RUN pip3 install --no-cache-dir -r gpu_worker/requirements.txt

COPY packages/ ./packages/
RUN pip3 install --no-cache-dir -e packages/ai_engine
COPY apps/api/app ./apps/api/app
COPY gpu_worker/ ./gpu_worker/
COPY comfyui/workflows ./comfyui/workflows

# Assumes a ComfyUI server + Ollama reachable via COMFYUI_URL / OLLAMA_HOST env.
CMD ["python3", "-m", "gpu_worker"]
