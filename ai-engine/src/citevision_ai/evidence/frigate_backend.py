"""Frigate evidence backend — delegates to frigate_track_evidence (SingleTrackWorker port)."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from citevision_ai.config import settings
from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence

logger = logging.getLogger(__name__)


class FrigateEvidenceBackend:
    """Thin wrapper kept for import compatibility; all capture goes through track evidence."""

    def __init__(self) -> None:
        self._track = FrigateTrackEvidence()

    def enabled(self) -> bool:
        return self._track.enabled()

    def frigate_camera_id(self, camera_id: str) -> str:
        return self._track.frigate_camera_id(camera_id)

    def capture(
        self,
        policy: dict[str, Any],
        evt: dict[str, Any],
        *,
        org_id: str,
        camera_id: str,
        aligned_frame: np.ndarray | None = None,
    ) -> dict[str, Any] | None:
        if aligned_frame is not None:
            logger.debug(
                "frigate_backend: ignoring aligned_frame (track evidence uses Frigate event only)",
            )
        if settings.evidence_backend.strip().lower() == "frigate":
            return self._track.capture(policy, evt, org_id=org_id, camera_id=camera_id)
        return self._track.capture(policy, evt, org_id=org_id, camera_id=camera_id)
