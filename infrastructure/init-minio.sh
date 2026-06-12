#!/bin/sh
set -e

echo "Waiting for MinIO..."
until mc alias set local http://minio:9000 "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}"; do
  sleep 2
done

echo "Creating bucket: ${MINIO_BUCKET}"
mc mb --ignore-existing "local/${MINIO_BUCKET}"

echo "Setting bucket policy to download-only for recordings"
mc anonymous set download "local/${MINIO_BUCKET}/public" 2>/dev/null || true

echo "MinIO initialization complete."
