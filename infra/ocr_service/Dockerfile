FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    OCR_PORT=8181 \
    HF_HOME=/models/hf \
    XDG_CACHE_HOME=/models/xdg \
    TORCH_HOME=/models/torch \
    HOME=/models/home

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Cache modèles Fast-ALPR / HF dans le volume /models (persiste entre rebuilds).
RUN mkdir -p /models/hf /models/xdg /models/torch /models/home/.cache/open-image-models

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
    && pip install --retries 10 --timeout 120 -r /app/requirements.txt

COPY server.py /app/server.py

EXPOSE 8181
HEALTHCHECK --interval=30s --timeout=90s --retries=5 --start-period=180s \
    CMD curl -fsS http://127.0.0.1:8181/healthz || exit 1

CMD ["python", "-u", "/app/server.py"]
