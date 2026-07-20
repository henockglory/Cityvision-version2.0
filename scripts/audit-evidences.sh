#!/usr/bin/env bash
# Wrapper audit preuves Postgres/MinIO (port mono/scripts/audit-evidences.sh)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 scripts/audit_evidence_quality.py "$@"
