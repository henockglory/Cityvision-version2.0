#!/bin/bash
cd ~/citevision-v2 || exit 1
source ai-engine/.venv/bin/activate 2>/dev/null
echo "=== Torch ==="
python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())" 2>&1
echo "=== Models ==="
ls -la shared/models/ 2>/dev/null | head -15
echo "=== ONNX ==="
ls shared/models/*.onnx 2>/dev/null | wc -l
echo "=== Health ==="
curl -sf http://localhost:8081/health 2>/dev/null | python3 -m json.tool 2>/dev/null | head -20
curl -sf http://localhost:8001/health 2>/dev/null | python3 -m json.tool 2>/dev/null | head -20 || echo "AI: DOWN"
echo "=== Processes ==="
ps aux | grep -E 'uvicorn|rules-engine|vite|ensure-ai|restart-api' | grep -v grep
