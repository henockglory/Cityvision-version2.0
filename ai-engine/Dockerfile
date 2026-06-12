FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e .

COPY models/ models/

ENV AI_ENGINE_HOST=0.0.0.0
ENV AI_ENGINE_PORT=8000
ENV YOLO_MODEL_PATH=/app/models/yolov8n.onnx

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "citevision_ai.main:app", "--host", "0.0.0.0", "--port", "8000"]
