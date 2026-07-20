#!/bin/bash
# Check what EVIDENCE_BACKEND the running AI process actually sees
AI_PID=$(pgrep -f 'uvicorn citevision_ai' | head -1)
if [ -n "$AI_PID" ]; then
  echo "AI PID: $AI_PID (started $(ps -p $AI_PID -o lstart= 2>/dev/null))"
  env_val=$(cat /proc/$AI_PID/environ 2>/dev/null | tr '\0' '\n' | grep EVIDENCE_BACKEND || echo "(not found in environ)")
  echo "  EVIDENCE_BACKEND in process env: $env_val"
else
  echo "AI process not running"
fi
echo "---"
echo "Current .env setting:"
grep EVIDENCE_BACKEND ~/citevision-v2/.env
