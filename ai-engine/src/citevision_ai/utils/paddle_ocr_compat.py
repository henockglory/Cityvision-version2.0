"""PaddleOCR v2/v3 compatible inference helpers."""
from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def paddle_gpu_available() -> bool:
    """True when the installed paddlepaddle build is compiled with CUDA."""
    try:
        import paddle

        return bool(paddle.device.is_compiled_with_cuda())
    except Exception:
        return False


def configure_paddle_runtime() -> None:
    """Disable oneDNN/MKLDNN before paddle/paddleocr import (WSL crash)."""
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("FLAGS_use_onednn", "0")
    os.environ.setdefault("FLAGS_enable_pir_api", "0")
    os.environ.setdefault("FLAGS_enable_pir_in_executor", "0")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    try:
        import paddle

        paddle.set_flags({"FLAGS_use_mkldnn": False})
    except Exception:
        pass


def default_paddle_ocr_kwargs(**overrides: Any) -> dict[str, Any]:
    """Shared PaddleOCR init — enable_mkldnn=False avoids PIR/oneDNN crash on CPU."""
    kw: dict[str, Any] = {
        "use_textline_orientation": True,
        "lang": "en",
        "enable_mkldnn": False,
    }
    kw.update(overrides)
    return kw


def create_paddle_ocr(**overrides: Any) -> Any:
    configure_paddle_runtime()
    from paddleocr import PaddleOCR

    kw = default_paddle_ocr_kwargs(**overrides)
    # GPU priority ([A.5]): use CUDA when the paddle build supports it, with a
    # safe fallback to CPU (and to a build that rejects the `device` kwarg).
    if "device" not in kw and paddle_gpu_available():
        try:
            ocr = PaddleOCR(**{**kw, "device": "gpu"})
            logger.info("PaddleOCR initialised on GPU")
            return ocr
        except Exception:
            logger.warning("PaddleOCR GPU init failed; falling back to CPU", exc_info=True)
    try:
        return PaddleOCR(**kw)
    except TypeError:
        # Older builds may reject some kwargs (e.g. device/use_textline_orientation).
        kw.pop("device", None)
        kw.pop("use_textline_orientation", None)
        return PaddleOCR(**kw)


def run_ocr(ocr: Any, image: np.ndarray) -> list[Any]:
    """Run OCR; try cls=True first (fast failure path), fall back to PaddleOCR 3.x predict()."""
    try:
        return ocr.ocr(image, cls=True)
    except TypeError:
        pass
    if hasattr(ocr, "predict"):
        try:
            return ocr.predict(image)
        except TypeError:
            pass
    return ocr.ocr(image)


def parse_ocr_lines(result: Any) -> list[tuple[str, float, list]]:
    """Normalize OCR output to (text, confidence, box) tuples."""
    lines: list[tuple[str, float, list]] = []
    if not result:
        return lines
    # v2: [[ [box, (text, conf)], ... ]]
    if isinstance(result, list) and result and isinstance(result[0], list):
        batch = result[0] or []
        for line in batch:
            if not line or len(line) < 2:
                continue
            box, meta = line[0], line[1]
            text = str(meta[0])
            conf = float(meta[1])
            lines.append((text, conf, box))
        return lines
    # v3 dict / object payloads — best-effort
    if isinstance(result, dict):
        for item in result.get("rec_texts") or result.get("texts") or []:
            if isinstance(item, str):
                lines.append((item, 1.0, []))
    return lines
