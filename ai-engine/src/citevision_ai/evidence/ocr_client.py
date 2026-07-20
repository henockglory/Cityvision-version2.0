"""HTTP client for the Fast-ALPR OCR service (ported from citevision_videoverbalisation)."""
from __future__ import annotations

import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def recognize_plate_jpeg(
    jpeg: bytes,
    ocr_url: str,
    *,
    timeout: float = 8.0,
) -> tuple[str, float, str]:
    """Return (plate_norm, confidence, source). Empty plate if OCR unavailable."""
    base = (ocr_url or "").strip().rstrip("/")
    if not base or not jpeg:
        return "", 0.0, "none"
    url = base if base.endswith("/ocr") else f"{base}/ocr"
    boundary = "----citevisionocrboundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="plate.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() + jpeg + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            import json
            data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        logger.debug("ocr service failed: %s", exc)
        return "", 0.0, "fast_alpr_unavailable"
    plate = str(data.get("plate") or data.get("plate_raw") or "").strip().upper()
    conf = float(data.get("confidence") or 0.0)
    return plate, conf, "fast_alpr"
