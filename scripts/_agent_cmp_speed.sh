#!/usr/bin/env bash
R="$HOME/citevision-v2/ai-engine/src/citevision_ai/analytics"
W=/mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/analytics
echo "=== runtime files ==="
ls -la "$R/zone_speed.py" "$R/zone_geometry.py" 2>&1
echo "=== runtime zone_speed: 100/default/distance ==="
grep -nE '100|DEFAULT|distance_m|resolve_speed' "$R/zone_speed.py" 2>&1 | head -30
echo "=== diff zone_speed (win -> runtime) ==="
diff <(sed 's/\r$//' "$W/zone_speed.py") "$R/zone_speed.py" | head -50
echo "=== diff zone_geometry (win -> runtime) ==="
diff <(sed 's/\r$//' "$W/zone_geometry.py") "$R/zone_geometry.py" 2>&1 | head -50
