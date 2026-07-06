#!/usr/bin/env bash
set -uo pipefail
export PATH="$PATH:/usr/local/go/bin"
W=/mnt/c/Users/gheno/citevision
R="$HOME/citevision-v2"

# Sync AI + rules-engine sources
cp "$W/ai-engine/src/citevision_ai/analytics/zone_speed.py" "$R/ai-engine/src/citevision_ai/analytics/zone_speed.py"
sed -i 's/\r$//' "$R/ai-engine/src/citevision_ai/analytics/zone_speed.py"
rsync -a "$W/rules-engine/cmd/" "$R/rules-engine/cmd/"
rsync -a "$W/rules-engine/internal/" "$R/rules-engine/internal/"
find "$R/rules-engine" -name '*.go' -exec sed -i 's/\r$//' {} +
echo SYNCED

cd "$R/rules-engine" && go build -o bin/rules-engine ./cmd/rules-engine 2>&1 && echo RULES_BUILD_OK
# Python syntax check for the AI change
python3 -c "import ast,sys; ast.parse(open('$R/ai-engine/src/citevision_ai/analytics/zone_speed.py').read()); print('AI_SYNTAX_OK')"
