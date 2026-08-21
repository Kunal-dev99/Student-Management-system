# One image runs both API and workers, selected by the container command (arch §19.1).
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

# API tier (default). Worker tier overrides the command in Kubernetes (arch §19.2).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
