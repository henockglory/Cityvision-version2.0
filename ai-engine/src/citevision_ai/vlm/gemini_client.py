"""Gemini 3.6 Flash VLM client — structured cabin / face verdicts (fail-closed)."""
from __future__ import annotations

import base64
import http.client
import json
import logging
import os
import re
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)

# WSL stub DNS + broken IPv6 routes cause intermittent "Temporary failure in name
# resolution" / handshake hangs under load. Prefer cached IPv4 + SNI.
_IPV4_CACHE: dict[str, tuple[str, float]] = {}
_IPV4_CACHE_TTL_SEC = 300.0


def _resolve_ipv4(host: str) -> str:
    now = time.time()
    cached = _IPV4_CACHE.get(host)
    if cached and (now - cached[1]) < _IPV4_CACHE_TTL_SEC:
        return cached[0]
    infos = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
    if not infos:
        raise OSError(f"no_ipv4_for_host:{host}")
    ip = str(infos[0][4][0])
    _IPV4_CACHE[host] = (ip, now)
    return ip


def _http_open(req: urllib.request.Request, timeout: float):
    """Open HTTPS preferring IPv4 (WSL-safe). Falls back to urllib if disabled."""
    force = str(os.environ.get("GEMINI_FORCE_IPV4", "1") or "1").strip().lower()
    if force in ("0", "false", "no", "off"):
        return urllib.request.urlopen(req, timeout=timeout)

    parsed = urlparse(req.full_url)
    host = parsed.hostname or ""
    if not host:
        return urllib.request.urlopen(req, timeout=timeout)
    port = int(parsed.port or 443)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    method = (req.get_method() or "GET").upper()
    body = req.data if isinstance(req.data, (bytes, bytearray)) else None
    headers = {k: v for k, v in req.header_items()}
    headers.setdefault("Host", host)

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            if attempt:
                _IPV4_CACHE.pop(host, None)
            ip = _resolve_ipv4(host)
            ctx = ssl.create_default_context()
            conn = http.client.HTTPSConnection(
                ip, port=port, timeout=timeout, context=ctx,
            )
            sock = socket.create_connection((ip, port), timeout=timeout)
            # SNI must use hostname, not the literal IP we connected to.
            conn.sock = ctx.wrap_socket(sock, server_hostname=host)
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()

            class _Resp:
                def __init__(self, r: http.client.HTTPResponse, c: http.client.HTTPSConnection):
                    self._r = r
                    self._c = c
                    self.status = int(r.status)
                    self.headers = r.headers

                def read(self, *a: Any, **k: Any) -> bytes:
                    return self._r.read(*a, **k)

                def __enter__(self) -> "_Resp":
                    return self

                def __exit__(self, *a: Any) -> None:
                    try:
                        self._r.close()
                    finally:
                        self._c.close()

            if resp.status >= 400:
                try:
                    resp.read()
                finally:
                    conn.close()
                raise urllib.error.HTTPError(
                    req.full_url, resp.status, resp.reason, resp.headers, None,
                )
            return _Resp(resp, conn)
        except urllib.error.HTTPError:
            raise
        except Exception as exc:  # noqa: BLE001 — retry DNS/connect once
            last_exc = exc
            if attempt == 0:
                logger.warning("gemini ipv4 open retry host=%s err=%s", host, exc)
                continue
            break
    assert last_exc is not None
    raise last_exc


@dataclass(frozen=True)
class GeminiVerdict:
    violation: bool
    rule: str
    confidence: float
    visible: bool
    reason_short: str
    signals: list[str]
    latency_ms: float
    raw_ok: bool
    error: str = ""
    plate_text: str = ""
    readable: bool = False


class GeminiClientError(Exception):
    """Typed failure from Gemini HTTP / parse path."""


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    m = _JSON_FENCE.search(raw)
    if m:
        raw = m.group(1).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start : end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _parse_verdict(data: dict[str, Any], *, expected_rule: str, latency_ms: float) -> GeminiVerdict:
    rule = str(data.get("rule") or expected_rule or "").strip()
    signals_raw = data.get("signals") or []
    signals: list[str] = []
    if isinstance(signals_raw, list):
        signals = [str(s) for s in signals_raw if s is not None][:12]
    try:
        conf = float(data.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    visible = bool(data.get("visible", False))
    violation = bool(data.get("violation", False))
    reason = str(data.get("reason_short") or "")[:120]
    plate_text = str(data.get("plate_text") or "").strip().upper().replace(" ", "")[:32]
    readable = bool(data.get("readable", bool(plate_text)))
    return GeminiVerdict(
        violation=violation,
        rule=rule or expected_rule,
        confidence=conf,
        visible=visible,
        reason_short=reason,
        signals=signals,
        latency_ms=latency_ms,
        raw_ok=True,
        plate_text=plate_text,
        readable=readable,
    )


_CABIN_RULES = frozenset({"seatbelt_violation", "phone_use_violation"})

CABIN_PROMPTS: dict[str, str] = {
    "seatbelt_violation": (
        "You analyze a FULL-VEHICLE bounding-box crop from a roadside/cabin camera "
        "(Frigate track crop — may be blurry, distant, low light, or partially occluded). "
        "Answer ONE yes/no question only: is the driver NOT wearing a seatbelt?\n"
        "Be lucid despite poor quality: look for shoulder-belt diagonal across the torso, "
        "or a clear absence of any belt. If you cannot tell with reasonable confidence, "
        "answer NO (violation=false) — do not invent a violation.\n"
        "Reply with ONLY one JSON object, no markdown:\n"
        '{"violation":bool,"rule":"seatbelt_violation","confidence":0.0-1.0,'
        '"reason_short":"<=120 chars"}\n'
        "violation=true means YES (seatbelt not worn). violation=false means NO "
        "(belt worn OR unclear/uncertain)."
    ),
    "phone_use_violation": (
        "You analyze a FULL-VEHICLE bounding-box crop from a roadside/cabin camera "
        "(Frigate track crop — may be blurry, distant, low light, or partially occluded). "
        "Answer ONE yes/no question only: is the driver using a phone while driving?\n"
        "Be lucid despite poor quality: look for a phone held to the ear or in front of the face, "
        "or hands clearly manipulating a handheld device. If you cannot tell with reasonable "
        "confidence, answer NO (violation=false) — do not invent a violation.\n"
        "Reply with ONLY one JSON object, no markdown:\n"
        '{"violation":bool,"rule":"phone_use_violation","confidence":0.0-1.0,'
        '"reason_short":"<=120 chars"}\n'
        "violation=true means YES (phone use). violation=false means NO "
        "(no phone OR unclear/uncertain)."
    ),
}


def cabin_prompt_text(rule: str, *, extra_context: str = "") -> str:
    """Exact prompt text sent (or that would be sent) for cabin gallery dumps."""
    prompt = CABIN_PROMPTS.get(rule) or ""
    if extra_context and prompt:
        prompt = f"{prompt}\nContext: {extra_context[:500]}"
    return prompt

PLATE_PROMPTS: dict[str, str] = {
    "plate_ocr": (
        "You read a vehicle license plate from a camera crop. "
        "Reply with ONLY one JSON object, no markdown:\n"
        '{"violation":bool,"rule":"plate_ocr","confidence":0.0-1.0,'
        '"visible":bool,"readable":bool,"plate_text":"STRING",'
        '"reason_short":"<=120 chars","signals":["..."]}\n'
        "plate_text must be the plate characters without spaces if readable, else empty. "
        "Set visible=false / readable=false if the plate is not clear. "
        "Set violation=true only when readable=true and plate_text is non-empty. "
        "If unclear, violation=false and signals must include \"unclear\"."
    ),
}

FACE_PROMPTS: dict[str, str] = {
    "face_detected": (
        "You analyze a camera frame crop. Decide if at least one human face is clearly visible. "
        "Reply ONLY JSON:\n"
        '{"violation":bool,"rule":"face_detected","confidence":0.0-1.0,'
        '"visible":bool,"reason_short":"<=120 chars","signals":["..."]}\n'
        "violation=true means a face is detected (not an infraction — detection event)."
    ),
    "face_unknown": (
        "You analyze a face crop. No watchlist match is provided. "
        "Confirm there is a clear human face (unknown identity). "
        "Reply ONLY JSON with rule \"face_unknown\". "
        "violation=true if a clear unmatched face is present."
    ),
    "face_watchlist_match": (
        "You compare the query face crop to reference watchlist description/context. "
        "Reply ONLY JSON with rule \"face_watchlist_match\". "
        "violation=true only if it is the same person with high confidence."
    ),
    "face_identity_compare": (
        "You compare ONE query face crop (first image) to reference watchlist face photos "
        "(subsequent images, each labeled). "
        "Reply ONLY JSON:\n"
        '{"violation":bool,"rule":"face_identity_compare","confidence":0.0-1.0,'
        '"visible":bool,"same_person":bool,"matched_label":"STRING_OR_EMPTY",'
        '"reason_short":"<=120 chars","signals":["..."]}\n'
        "Set same_person=true and violation=true ONLY if the query face is clearly the same "
        "person as one reference, with high confidence. "
        "matched_label must be the exact reference label when same_person=true, else empty. "
        "If unclear, blurry, occluded, or no confident match: same_person=false, violation=false, "
        "signals must include \"unclear\"."
    ),
}

ROAD_PROMPTS: dict[str, str] = {
    "red_light_violation": (
        "You analyze a traffic-camera crop that may show a traffic light and/or a vehicle "
        "in a red-light observation / crossing zone. "
        "Task: decide if the visible signal is RED and a vehicle is (or was) crossing against it. "
        "Reply with ONLY one JSON object, no markdown:\n"
        '{"violation":bool,"rule":"red_light_violation","confidence":0.0-1.0,'
        '"visible":bool,"reason_short":"<=120 chars","signals":["..."]}\n'
        "Set visible=false if the light is not clear enough. "
        "Set violation=true only if you are confident the light is red AND a vehicle is committing "
        "or has clearly crossed on red. "
        "If unclear, violation=false and signals must include \"unclear\"."
    ),
}


class GeminiClient:
    """Thin HTTP client for Gemini generateContent (image + text → structured JSON)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-3.6-flash",
        timeout: float = 20.0,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._model = (model or "gemini-3.6-flash").strip()
        self._timeout = float(timeout) if timeout and timeout > 0 else 20.0

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    @property
    def model(self) -> str:
        return self._model

    def ping(self) -> bool:
        """Cheap reachability: models list (no image). Fail-closed on errors."""
        if not self.configured:
            return False
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self._api_key}"
        req = urllib.request.Request(url, method="GET")
        try:
            with _http_open(req, timeout=min(8.0, self._timeout)) as resp:
                return int(getattr(resp, "status", 200) or 200) < 400
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
            return False

    def judge_jpeg(
        self,
        jpeg: bytes,
        *,
        rule: str,
        extra_context: str = "",
    ) -> GeminiVerdict:
        """Return a fail-closed verdict; never invents a violation on transport/parse errors."""
        t0 = time.perf_counter()
        if not self.configured:
            return GeminiVerdict(
                False, rule, 0.0, False, "", [], 0.0, False, error="not_configured",
            )
        if not jpeg:
            return GeminiVerdict(
                False, rule, 0.0, False, "", [], 0.0, False, error="empty_jpeg",
            )
        prompt = (
            CABIN_PROMPTS.get(rule)
            or FACE_PROMPTS.get(rule)
            or PLATE_PROMPTS.get(rule)
            or ROAD_PROMPTS.get(rule)
        )
        if not prompt:
            return GeminiVerdict(
                False, rule, 0.0, False, "", [], 0.0, False, error="unknown_rule",
            )
        if extra_context:
            prompt = f"{prompt}\nContext: {extra_context[:500]}"
        jpeg = _downscale_jpeg(jpeg, max_side=768, quality=80)
        b64 = base64.b64encode(jpeg).decode("ascii")
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1024,
                "responseMimeType": "application/json",
            },
        }
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:generateContent?key={self._api_key}"
        )
        raw_body = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=raw_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with _http_open(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            ms = (time.perf_counter() - t0) * 1000.0
            code = int(getattr(exc, "code", 0) or 0)
            err = "rate_limited" if code == 429 else "http_error"
            logger.warning("gemini request failed rule=%s: HTTP %s", rule, code)
            return GeminiVerdict(
                False, rule, 0.0, False, "", [], ms, False, error=err,
            )
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            ValueError,
            http.client.HTTPException,
        ) as exc:
            ms = (time.perf_counter() - t0) * 1000.0
            logger.warning("gemini request failed rule=%s: %s", rule, exc)
            return GeminiVerdict(
                False, rule, 0.0, False, "", [], ms, False, error="http_error",
            )
        ms = (time.perf_counter() - t0) * 1000.0
        text = _candidate_text(payload)
        data = _extract_json_object(text)
        if not data:
            logger.warning(
                "gemini invalid JSON rule=%s preview=%r",
                rule, (text or "")[:180],
            )
            return GeminiVerdict(
                False, rule, 0.0, False, "", [], ms, False, error="invalid_json",
            )
        verdict = _parse_verdict(data, expected_rule=rule, latency_ms=ms)
        # Fail-closed: rule mismatch → no violation
        if verdict.rule and expected_rule_ok(verdict.rule, rule) is False:
            return GeminiVerdict(
                False, rule, verdict.confidence, verdict.visible,
                verdict.reason_short, verdict.signals, ms, True, error="rule_mismatch",
            )
        return verdict

    def compare_faces(
        self,
        query_jpeg: bytes,
        references: list[tuple[str, bytes]],
        *,
        min_confidence: float = 0.75,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Multimodal same-person vote vs watchlist reference photos (fail-closed)."""
        t0 = time.perf_counter()
        if not self.configured:
            return {"match": False, "status": "skipped", "error": "not_configured"}
        if not query_jpeg:
            return {"match": False, "status": "skipped", "error": "empty_jpeg"}
        if not references:
            return {"match": False, "status": "skipped", "error": "no_references"}

        prompt = FACE_PROMPTS["face_identity_compare"]
        labels = [lab for lab, _ in references if lab]
        if labels:
            prompt += "\nReference labels in order: " + ", ".join(labels[:12])

        parts: list[dict[str, Any]] = [{"text": prompt}]
        q = _downscale_jpeg(query_jpeg, max_side=640, quality=80)
        parts.append({"text": "QUERY_FACE:"})
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(q).decode("ascii"),
            }
        })
        for lab, ref in references[:6]:
            rj = _downscale_jpeg(ref, max_side=512, quality=80)
            parts.append({"text": f"REFERENCE_LABEL={lab}"})
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(rj).decode("ascii"),
                }
            })

        body = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1024,
                "responseMimeType": "application/json",
            },
        }
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:generateContent?key={self._api_key}"
        )
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        to = float(timeout) if timeout and timeout > 0 else min(self._timeout, 15.0)
        try:
            with _http_open(req, timeout=to) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            code = int(getattr(exc, "code", 0) or 0)
            err = "rate_limited" if code == 429 else "http_error"
            return {
                "match": False,
                "status": "error",
                "error": err,
                "latency_ms": (time.perf_counter() - t0) * 1000.0,
            }
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            ValueError,
            http.client.HTTPException,
        ) as exc:
            err = "timeout" if "timed out" in str(exc).lower() or isinstance(exc, TimeoutError) else "http_error"
            return {
                "match": False,
                "status": "timeout" if err == "timeout" else "error",
                "error": err,
                "latency_ms": (time.perf_counter() - t0) * 1000.0,
            }

        text = _candidate_text(payload)
        data = _extract_json_object(text) or {}
        same = bool(data.get("same_person") or data.get("violation"))
        conf = data.get("confidence")
        try:
            conf_f = float(conf) if conf is not None else 0.0
        except (TypeError, ValueError):
            conf_f = 0.0
        matched = str(data.get("matched_label") or "").strip()
        # Fail-closed: require threshold + known label
        known = {lab.lower(): lab for lab, _ in references if lab}
        if matched and matched.lower() in known:
            matched = known[matched.lower()]
        elif matched:
            # allow exact case-insensitive contains against reference labels
            hit = next((lab for lab in known.values() if lab.lower() == matched.lower()), "")
            matched = hit
        ok = same and conf_f >= float(min_confidence) and bool(matched)
        return {
            "match": ok,
            "label": matched if ok else None,
            "score": conf_f,
            "status": "ok",
            "source": "gemini_multimodal",
            "same_person": same,
            "latency_ms": (time.perf_counter() - t0) * 1000.0,
            "reason_short": str(data.get("reason_short") or "")[:120],
        }


def _candidate_text(payload: dict[str, Any]) -> str:
    """Join all text parts (Gemini 3.x may interleave thoughtSignature / text)."""
    try:
        cands = payload.get("candidates") or []
        parts = (((cands[0] or {}).get("content") or {}).get("parts") or [])
    except (IndexError, TypeError, AttributeError):
        return ""
    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        t = part.get("text")
        if t:
            chunks.append(str(t))
    return "\n".join(chunks).strip()


def _downscale_jpeg(jpeg: bytes, *, max_side: int = 768, quality: int = 80) -> bytes:
    """Bound egress size for free-tier latency / token cost."""
    if not jpeg or len(jpeg) < 40_000:
        return jpeg
    try:
        import cv2
        import numpy as np

        arr = np.frombuffer(jpeg, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return jpeg
        h, w = img.shape[:2]
        scale = min(1.0, float(max_side) / float(max(h, w, 1)))
        if scale < 0.999:
            img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))))
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        return buf.tobytes() if ok else jpeg
    except Exception:
        return jpeg


def expected_rule_ok(got: str, expected: str) -> bool:
    g, e = got.strip(), expected.strip()
    return not g or g == e


def should_emit(verdict: GeminiVerdict, *, min_confidence: float) -> bool:
    """Canonical emit gate for cabin/face/plate (violation=true means positive detection)."""
    if not verdict.raw_ok or verdict.error:
        return False
    if verdict.rule in _CABIN_RULES:
        return bool(verdict.violation)
    if not verdict.visible:
        return False
    if "unclear" in {s.lower() for s in verdict.signals}:
        return False
    if verdict.rule == "plate_ocr" or (verdict.plate_text and "plate" in (verdict.rule or "")):
        if not verdict.readable or not verdict.plate_text:
            return False
        return float(verdict.confidence) >= float(min_confidence)
    if not verdict.violation:
        return False
    return float(verdict.confidence) >= float(min_confidence)
