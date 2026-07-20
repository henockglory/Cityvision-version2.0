#!/usr/bin/env bash
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -c "SELECT id, name FROM organizations LIMIT 5;"
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -c "SELECT id, name FROM cameras ORDER BY name LIMIT 20;"
