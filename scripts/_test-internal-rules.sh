#!/usr/bin/env bash
curl -sf -H "X-Internal-Key: changeme_internal_service_key" \
  "http://localhost:8081/api/v1/internal/orgs/99c16650-b07f-4acb-a999-dfc98941406f/rules/active" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('active rules from API:', len(d))"
