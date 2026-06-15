from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


class EvidenceUploader:
    def __init__(self) -> None:
        self.backend_url = os.getenv("BACKEND_API_URL", "http://localhost:8081").rstrip("/")
        self.internal_key = os.getenv("INTERNAL_API_KEY", "")
        self.timeout = float(os.getenv("EVIDENCE_UPLOAD_TIMEOUT", "8"))

    def upload(
        self,
        org_id: str,
        camera_id: str,
        event_id: str,
        scene_jpeg: bytes | None,
        subject_jpeg: bytes | None,
        clip_mp4: bytes | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not org_id or not camera_id:
            return None
        url = f"{self.backend_url}/api/v1/internal/orgs/{org_id}/evidence/upload"
        headers = {}
        if self.internal_key:
            headers["X-Internal-Key"] = self.internal_key
        files: dict[str, tuple] = {}
        if clip_mp4:
            files["clip"] = ("clip.mp4", clip_mp4, "video/mp4")
        if scene_jpeg:
            files["scene"] = ("scene.jpg", scene_jpeg, "image/jpeg")
        if subject_jpeg:
            files["subject"] = ("subject.jpg", subject_jpeg, "image/jpeg")
        if not files:
            return None
        data = {
            "camera_id": camera_id,
            "event_id": event_id or "",
            "metadata": json.dumps(metadata or {}),
        }
        try:
            resp = requests.post(url, headers=headers, data=data, files=files, timeout=self.timeout)
            if resp.status_code >= 400:
                logger.warning("evidence upload HTTP %s: %s", resp.status_code, resp.text[:200])
                return None
            body = resp.json()
            return body.get("evidence") or body
        except Exception as exc:
            logger.warning("evidence upload failed: %s", exc)
            return None
