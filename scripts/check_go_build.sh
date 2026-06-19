#!/usr/bin/env bash
set -e
export PATH="$PATH:/usr/local/go/bin:/home/gheno/go/bin:/usr/local/go/bin"
cd ~/citevision-v2/backend
echo "Go version: $(go version 2>/dev/null || echo 'not found')"
go build ./internal/camera/... 2>&1 && echo "BUILD OK" || echo "BUILD FAILED"
