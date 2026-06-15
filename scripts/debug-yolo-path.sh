#!/usr/bin/env bash
cd ~/citevision-v2/ai-engine
source .venv/bin/activate
set -a; source ../.env; set +a
python -c "from citevision_ai.config import settings; p=settings.resolved_yolo_path(); print(p, p.exists())"
