#!/usr/bin/env bash
set -euo pipefail
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -c "SELECT 'evidence_objects', count(*) FROM evidence_objects;"
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -c "SELECT 'alerts', count(*) FROM alerts;"
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -c "SELECT 'events', count(*) FROM events;"
echo "--- per camera ---"
sudo du -sh /var/lib/docker/volumes/infra_minio_data/_data/citevision-evidence/orgs/*/cameras/* 2>/dev/null | sort -hr
