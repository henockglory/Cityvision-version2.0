#!/usr/bin/env bash
set -uo pipefail
echo "=== health ==="
curl -sf --max-time 3 http://127.0.0.1:8081/health && echo backend_ok || echo backend_down
curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null && echo ai_ok || echo ai_down
curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null && echo rules_ok || echo rules_down
curl -sf --max-time 3 http://127.0.0.1:5000/api/version && echo || echo frigate_down
pgrep -af '_validate_rule_frigate|_run_1hit' || echo no_validator
python3 - <<'PY'
from pathlib import Path
import re
text=Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml").read_text()
cam="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
for key in ("record","snapshots"):
    m=re.search(rf"{re.escape(cam)}:.*?{key}:\s*\n\s*enabled:\s*(true|false)", text, re.S)
    print(key, m.group(1) if m else "?")
PY
