#!/usr/bin/env bash
set -e
export PATH="$PATH:/usr/local/go/bin:/home/gheno/go/bin"
cd ~/citevision-v2/backend
go build ./... 2>&1 && echo "FULL BACKEND BUILD OK" || echo "FULL BACKEND BUILD FAILED"
