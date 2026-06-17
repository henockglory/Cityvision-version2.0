#!/usr/bin/env bash
# Vérifie livraison webhook CloudEvents + retry (httptest via go test)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/usr/local/go/bin:$PATH"
cd "$ROOT/backend"
go test ./internal/routing/... -run 'TestPostWebhook' -count=1 -v
echo "=== verify-e2e-webhook-cloudevents OK ==="
