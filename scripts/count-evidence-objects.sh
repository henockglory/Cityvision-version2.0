#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/lib/env-utils.sh"
load_dotenv "$(ensure_env_file "$ROOT")"
python3 <<'PY'
import os
from minio import Minio
endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9003").replace("http://", "").replace("https://", "")
c = Minio(endpoint, access_key=os.environ["MINIO_ACCESS_KEY"], secret_key=os.environ["MINIO_SECRET_KEY"], secure=False)
bucket = os.environ.get("MINIO_BUCKET", "citevision-evidence")
objs = list(c.list_objects(bucket, prefix="orgs/", recursive=True))
print("object_count", len(objs))
for o in objs[:5]:
    print(o.object_name)
PY
