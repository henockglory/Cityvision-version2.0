#!/usr/bin/env bash
set -euo pipefail
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT evidence_snapshot::text FROM alerts WHERE id='748002fa-4fa8-46bb-ac43-adabb1972a14'::uuid;" \
  | python3 -c "import sys,json; s=sys.stdin.read().strip(); j=json.loads(s); pkg=j.get('package') or j; print('top keys', sorted(j.keys())); print('pkg keys', sorted(pkg.keys())); print('pipe in json', '|' in s); print('images', len(pkg.get('images') or []))"
