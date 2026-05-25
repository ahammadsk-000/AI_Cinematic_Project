# CPU-only control-plane image. Deliberately slim — NO torch/diffusers.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

# system deps for asyncpg/bcrypt build wheels are prebuilt; keep image minimal
COPY apps/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api/ ./
# storage is bind-mounted in compose; create the mountpoint so it exists standalone
RUN mkdir -p /app/storage

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
