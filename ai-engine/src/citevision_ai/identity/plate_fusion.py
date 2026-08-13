"""Fuse Gemini OCR + PaddleOCR readings (best confidence wins) with composition filter."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from citevision_ai.identity.plate import PaddleOcrPlateBackend

logger = logging.getLogger(__name__)

_PLATE_RE = re.compile(r"^[A-Z0-9]{4,12}$")
_paddle_backend: PaddleOcrPlateBackend | None = None


@dataclass(frozen=True)
class PlateReading:
    text: str
    confidence: float
    source: str


@dataclass
class PlatePatternSpec:
    id: str
    name: str
    mode: str  # standard | custom
    regex: str
    is_default: bool = False


class PlatePatternCatalog:
    """Org plate composition patterns synced from backend."""

    def __init__(self) -> None:
        self._by_id: dict[str, PlatePatternSpec] = {}
        self._default_id: str | None = None
        self._compiled: dict[str, re.Pattern[str]] = {}

    def set_patterns(self, patterns: list[dict[str, Any]] | None) -> None:
        self._by_id.clear()
        self._compiled.clear()
        self._default_id = None
        for raw in patterns or []:
            if not isinstance(raw, dict):
                continue
            pid = str(raw.get("id") or "").strip()
            if not pid:
                continue
            mode = str(raw.get("mode") or "custom").strip().lower()
            regex = str(raw.get("regex") or "").strip()
            spec = PlatePatternSpec(
                id=pid,
                name=str(raw.get("name") or pid),
                mode=mode,
                regex=regex,
                is_default=bool(raw.get("is_default")),
            )
            self._by_id[pid] = spec
            if spec.is_default:
                self._default_id = pid
            if mode == "custom" and regex:
                try:
                    self._compiled[pid] = re.compile(regex)
                except re.error:
                    logger.warning("invalid plate pattern regex id=%s re=%s", pid, regex)

    def resolve(
        self,
        pattern_id: str | None,
        *,
        use_org_default: bool = True,
    ) -> re.Pattern[str] | None:
        """Return compiled custom regex, or None for standard alnum 4–12.

        - missing/empty → org default custom pattern if any, else standard
        - ``standard`` → always standard (ignores org default)
        - uuid → named pattern (custom regex or standard mode)
        """
        pid = (pattern_id or "").strip()
        if pid in ("standard", "generic", "default_standard"):
            return None
        if not pid:
            if use_org_default and self._default_id:
                return self._compiled.get(self._default_id)
            return None
        spec = self._by_id.get(pid)
        if not spec:
            if use_org_default and self._default_id:
                return self._compiled.get(self._default_id)
            return None
        if spec.mode != "custom":
            return None
        return self._compiled.get(pid)


_catalog = PlatePatternCatalog()


def get_plate_pattern_catalog() -> PlatePatternCatalog:
    return _catalog


def set_plate_patterns(patterns: list[dict[str, Any]] | None) -> None:
    _catalog.set_patterns(patterns)


def _normalize_plate(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())[:32]


def matches_composition(
    text: str,
    pattern_re: re.Pattern[str] | str | None = None,
) -> bool:
    """True when normalized text matches active composition (or standard)."""
    t = _normalize_plate(text)
    if not t:
        return False
    cre = _coerce_pattern(pattern_re)
    if cre is not None:
        return bool(cre.match(t))
    return bool(_PLATE_RE.match(t))


def _valid_plate(
    text: str,
    pattern_re: re.Pattern[str] | str | None = None,
) -> bool:
    return matches_composition(text, pattern_re)


def get_paddle_backend() -> PaddleOcrPlateBackend:
    global _paddle_backend
    if _paddle_backend is None:
        _paddle_backend = PaddleOcrPlateBackend()
        _paddle_backend.load()
    return _paddle_backend


def run_paddle_on_jpeg(
    jpeg: bytes,
    pattern_re: re.Pattern[str] | str | None = None,
) -> PlateReading | None:
    if not jpeg:
        return None
    backend = get_paddle_backend()
    if not backend.is_loaded:
        return None
    arr = np.frombuffer(jpeg, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        return None
    results = backend.recognize(img)
    if not results:
        return None
    cre = _coerce_pattern(pattern_re)
    candidates: list[PlateReading] = []
    for r in results:
        text = _normalize_plate(r.text)
        if not _valid_plate(text, cre):
            continue
        candidates.append(
            PlateReading(text=text, confidence=float(r.confidence or 0.0), source="paddle")
        )
    if not candidates:
        return None
    return max(candidates, key=lambda x: x.confidence)


def reading_from_gemini_verdict(
    verdict: Any,
    pattern_re: re.Pattern[str] | str | None = None,
) -> PlateReading | None:
    text = _normalize_plate(str(getattr(verdict, "plate_text", "") or ""))
    cre = _coerce_pattern(pattern_re)
    if not _valid_plate(text, cre):
        return None
    conf = float(getattr(verdict, "confidence", 0.0) or 0.0)
    if not getattr(verdict, "readable", True) and conf < 0.35:
        return None
    return PlateReading(text=text, confidence=conf, source="gemini")


def filter_plate_candidates(
    readings: list[tuple[str, float, str]],
    pattern_re: re.Pattern[str] | str | None = None,
) -> list[tuple[str, float, str]]:
    """Keep only composition-matching readings; used by evidence OCR fusion."""
    cre = _coerce_pattern(pattern_re)
    out: list[tuple[str, float, str]] = []
    for text, conf, src in readings:
        norm = _normalize_plate(text)
        if _valid_plate(norm, cre):
            out.append((norm, float(conf), src))
    return out


def fuse_plate_readings(
    gemini: PlateReading | None,
    paddle: PlateReading | None,
) -> tuple[PlateReading | None, dict[str, Any]]:
    """Return best reading + fusion metadata."""
    meta: dict[str, Any] = {
        "ocr_gemini": gemini.text if gemini else "",
        "ocr_gemini_conf": round(gemini.confidence, 3) if gemini else 0.0,
        "ocr_paddle": paddle.text if paddle else "",
        "ocr_paddle_conf": round(paddle.confidence, 3) if paddle else 0.0,
    }
    if gemini and paddle:
        if gemini.text == paddle.text:
            winner = PlateReading(
                text=gemini.text,
                confidence=max(gemini.confidence, paddle.confidence),
                source="both",
            )
        elif gemini.confidence >= paddle.confidence:
            winner = gemini
        else:
            winner = paddle
    elif gemini:
        winner = gemini
    elif paddle:
        winner = paddle
    else:
        meta["ocr_winner"] = ""
        return None, meta
    meta["ocr_winner"] = winner.source
    return winner, meta


def _coerce_pattern(pattern_re: re.Pattern[str] | str | None) -> re.Pattern[str] | None:
    if pattern_re is None:
        return None
    if isinstance(pattern_re, re.Pattern):
        return pattern_re
    s = str(pattern_re).strip()
    if not s:
        return None
    try:
        return re.compile(s)
    except re.error:
        logger.warning("invalid plate pattern regex %s", s)
        return None


def resolve_zone_plate_pattern(zinfo: dict[str, Any] | None) -> re.Pattern[str] | None:
    """Resolve composition regex from zone behavior_config.plate_pattern_id."""
    if not zinfo:
        return _catalog.resolve(None)
    bcfg = zinfo.get("behavior_config") if isinstance(zinfo.get("behavior_config"), dict) else {}
    cfg = bcfg.get("config") if isinstance(bcfg.get("config"), dict) else {}
    if not cfg and isinstance(zinfo.get("config"), dict):
        cfg = zinfo["config"]
    meta = zinfo.get("metadata") if isinstance(zinfo.get("metadata"), dict) else {}
    pid = str(
        cfg.get("plate_pattern_id")
        or zinfo.get("plate_pattern_id")
        or meta.get("plate_pattern_id")
        or ""
    ).strip()
    return _catalog.resolve(pid or None)
