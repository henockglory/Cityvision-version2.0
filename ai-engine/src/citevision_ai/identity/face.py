from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from citevision_ai.face.insightface_stub import FaceRecognizer

logger = logging.getLogger(__name__)


def watchlist_photo_dir() -> Path:
    raw = str(os.environ.get("WATCHLIST_PHOTO_DIR") or "").strip()
    if raw:
        return Path(raw)
    return Path(os.environ.get("VLM_FACE_DUMP_DIR") or "/tmp/citevision-watchlist-photos").parent / "watchlist_photos"


def save_watchlist_photo(identifier: str, jpeg: bytes) -> str:
    """Persist enrollment JPEG for Gemini multimodal compare (local cache)."""
    if not jpeg or not identifier:
        return ""
    root = watchlist_photo_dir()
    root.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.\-]+", "_", identifier.strip())[:80] or "face"
    path = root / f"{safe}.jpg"
    path.write_bytes(jpeg)
    return str(path)


class InsightFaceRecognizer(FaceRecognizer):
    """Production InsightFace face detection and embedding."""

    def __init__(self, model_name: str = "buffalo_l", model_root: str = "models/insightface") -> None:
        self.model_name = model_name
        self.model_root = model_root
        self._app = None
        self._loaded = False
        self._device = "cpu"

    def load(self) -> None:
        try:
            from insightface.app import FaceAnalysis

            # [G.62]/[P.132] GPU priority, CPU last resort ([A.5]). The previous
            # config forced providers=["CPUExecutionProvider"] even with ctx_id=0,
            # so InsightFace ran on CPU. Auto-detect CUDA and prefer it.
            providers = ["CPUExecutionProvider"]
            ctx_id = -1
            try:
                import onnxruntime as ort

                if "CUDAExecutionProvider" in ort.get_available_providers():
                    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                    ctx_id = 0
            except Exception:
                logger.warning("onnxruntime provider probe failed; InsightFace on CPU")

            self._app = FaceAnalysis(
                name=self.model_name,
                root=self.model_root,
                providers=providers,
            )
            self._app.prepare(ctx_id=ctx_id, det_size=(640, 640))
            self._loaded = True
            self._device = "cuda" if ctx_id >= 0 else "cpu"
            logger.info("InsightFace loaded: %s (device=%s)", self.model_name, self._device)
        except Exception:
            logger.exception("InsightFace load failed")
            self._loaded = False

    @property
    def device(self) -> str:
        return self._device

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self._app is not None

    def detect_faces(self, frame: np.ndarray) -> list[dict[str, Any]]:
        if not self.is_loaded:
            return []
        faces = self._app.get(frame)
        results = []
        for f in faces:
            bbox = f.bbox.astype(float)
            results.append({
                "bbox": {
                    "x": float(bbox[0]),
                    "y": float(bbox[1]),
                    "width": float(bbox[2] - bbox[0]),
                    "height": float(bbox[3] - bbox[1]),
                },
                "embedding": f.embedding.tolist() if f.embedding is not None else None,
                "confidence": float(getattr(f, "det_score", 0.9)),
            })
        return results


class FaceIdentityEngine:
    """Matches detected faces against org watchlist."""

    def __init__(self, recognizer: FaceRecognizer | None = None, match_threshold: float = 0.45) -> None:
        self.recognizer = recognizer or InsightFaceRecognizer()
        self.match_threshold = match_threshold
        self._watchlist: list[dict[str, Any]] = []
        self._last_refresh = 0.0
        self._refresh_interval = 60.0
        self._process_every_n = 5
        self._frame_counter = 0
        self._gemini_enabled = False
        self._vlm_queue: Any = None
        self._frigate_bridge_active = False
        self._cooldown: dict[tuple[str, str], float] = {}
        self._cooldown_sec = 8.0

    def configure_gemini(self, enabled: bool, vlm_queue: Any = None) -> None:
        self._gemini_enabled = bool(enabled) and vlm_queue is not None
        self._vlm_queue = vlm_queue if self._gemini_enabled else None
        if self._gemini_enabled:
            logger.info("FaceIdentityEngine: Gemini VLM path available (InsightFace preferred when loaded)")

    def set_frigate_bridge_active(self, active: bool) -> None:
        """Frigate bridge owns face: InsightFace/Gemini run on Frigate crops only (XOR)."""
        self._frigate_bridge_active = bool(active)
        if self._frigate_bridge_active:
            logger.info(
                "FaceIdentityEngine: Frigate bridge ON — full-frame InsightFace/Gemini disabled; "
                "match_jpeg on Frigate crops only",
            )

    def load(self) -> None:
        if hasattr(self.recognizer, "load"):
            self.recognizer.load()

    @property
    def is_loaded(self) -> bool:
        if hasattr(self.recognizer, "is_loaded") and bool(self.recognizer.is_loaded):
            return True
        # Honest: Gemini can emit face_detected without InsightFace weights.
        return bool(self._gemini_enabled)

    def set_watchlist(self, entries: list[dict[str, Any]]) -> None:
        self._watchlist = list(entries or [])
        self._last_refresh = time.monotonic()
        # Best-effort: if metadata carries photo bytes path already on disk, keep it.
        logger.info("face watchlist set entries=%d", len(self._watchlist))

    def embed_jpeg(self, jpeg: bytes) -> dict[str, Any]:
        """Return best face embedding from a still image (enrollment path)."""
        import cv2

        if not jpeg:
            return {"embedding": [], "face_count": 0, "error": "empty_jpeg"}
        if not (hasattr(self.recognizer, "is_loaded") and self.recognizer.is_loaded):
            return {"embedding": [], "face_count": 0, "error": "insightface_not_loaded"}
        arr = np.frombuffer(jpeg, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return {"embedding": [], "face_count": 0, "error": "decode_failed"}
        faces = self.recognizer.detect_faces(frame)
        if not faces:
            return {"embedding": [], "face_count": 0, "error": "no_face"}
        best = max(faces, key=lambda f: float(f.get("confidence") or 0.0))
        emb = best.get("embedding")
        if not emb:
            return {"embedding": [], "face_count": len(faces), "error": "no_embedding"}
        return {
            "embedding": list(emb),
            "face_count": len(faces),
            "confidence": float(best.get("confidence") or 0.0),
            "bbox": best.get("bbox"),
        }

    def match_vote_from_jpeg(self, jpeg: bytes) -> dict[str, Any]:
        """Single InsightFace vote dict for fusion (not full event emit list)."""
        events = self.match_jpeg(jpeg)
        best_score = None
        best_label = None
        best_id = None
        face_seen = False
        for ev in events:
            et = str(ev.get("event_type") or "")
            meta = ev.get("metadata") or {}
            if et == "face_detected":
                face_seen = True
            if et == "face_watchlist_match":
                score = meta.get("embedding_score", meta.get("confidence"))
                try:
                    score_f = float(score) if score is not None else 0.0
                except (TypeError, ValueError):
                    score_f = 0.0
                if best_score is None or score_f > best_score:
                    best_score = score_f
                    best_label = meta.get("label")
                    best_id = meta.get("identifier")
                    face_seen = True
            if et == "face_unknown":
                face_seen = True
        if best_label:
            return {
                "match": True,
                "label": best_label,
                "identifier": best_id,
                "score": best_score,
                "status": "ok",
                "source": "insightface_on_frigate_crop",
                "face_clear": True,
            }
        return {
            "match": False,
            "label": None,
            "score": best_score,
            "status": "ok" if face_seen else "no_face",
            "source": "insightface_on_frigate_crop",
            "face_clear": face_seen,
        }

    def reference_photo_for(
        self,
        *,
        identifier: str | None = None,
        label: str | None = None,
    ) -> bytes | None:
        """Load a single enrollment JPEG for the matched watchlist entry."""
        ident = str(identifier or "").strip()
        lab = str(label or "").strip()
        if not ident and not lab:
            return None
        root = watchlist_photo_dir()

        def _paths_for(entry: dict[str, Any]) -> list[str]:
            meta = entry.get("metadata") or {}
            paths: list[str] = []
            for key in ("ai_photo_path", "photo_path"):
                p = str(meta.get(key) or "").strip()
                if p:
                    paths.append(p)
            for candidate in (
                str(entry.get("identifier") or "").strip(),
                str(entry.get("label") or "").strip(),
                ident,
                lab,
            ):
                if not candidate:
                    continue
                safe = re.sub(r"[^A-Za-z0-9_.\-]+", "_", candidate)[:80]
                paths.append(str(root / f"{safe}.jpg"))
            return paths

        def _read_first(paths: list[str]) -> bytes | None:
            for p in paths:
                try:
                    data = Path(p).read_bytes()
                except OSError:
                    continue
                if data:
                    return data
            return None

        for entry in self._watchlist:
            e_lab = str(entry.get("label") or "").strip()
            e_id = str(entry.get("identifier") or "").strip()
            matched = False
            if ident and ident in (e_id, e_lab):
                matched = True
            if lab and lab in (e_lab, e_id):
                matched = True
            if not matched:
                continue
            data = _read_first(_paths_for(entry))
            if data:
                return data
        for ref_lab, data in self.reference_photos(max_n=12):
            if (lab and ref_lab == lab) or (ident and ref_lab == ident):
                return data
        return None

    def reference_photos(self, max_n: int = 6) -> list[tuple[str, bytes]]:
        """Load up to max_n local watchlist reference JPEGs for Gemini compare."""
        out: list[tuple[str, bytes]] = []
        root = watchlist_photo_dir()
        for entry in self._watchlist:
            if len(out) >= max_n:
                break
            label = str(entry.get("label") or entry.get("identifier") or "").strip()
            if not label:
                continue
            meta = entry.get("metadata") or {}
            paths: list[str] = []
            for key in ("ai_photo_path", "photo_path"):
                p = str(meta.get(key) or "").strip()
                if p:
                    paths.append(p)
            ident = str(entry.get("identifier") or "").strip()
            if ident:
                paths.append(str(root / f"{re.sub(r'[^A-Za-z0-9_.\\-]+', '_', ident)[:80]}.jpg"))
            # also try label-based filename
            safe_lab = re.sub(r"[^A-Za-z0-9_.\-]+", "_", label)[:80]
            paths.append(str(root / f"{safe_lab}.jpg"))
            for p in paths:
                try:
                    data = Path(p).read_bytes()
                except OSError:
                    continue
                if data:
                    out.append((label, data))
                    break
        return out

    def process_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        timestamp: str,
    ) -> list[dict[str, Any]]:
        # XOR: Frigate bridge owns face — never InsightFace/Gemini on full RTSP frame.
        if self._frigate_bridge_active:
            return []
        self._frame_counter += 1
        if self._frame_counter % self._process_every_n != 0:
            return []

        if hasattr(self.recognizer, "is_loaded") and self.recognizer.is_loaded:
            return self._process_insightface(camera_id, frame, timestamp)

        if self._gemini_enabled and self._vlm_queue is not None:
            self._enqueue_gemini_face(camera_id, frame, timestamp)
            return []
        return []

    def match_jpeg(self, jpeg: bytes) -> list[dict[str, Any]]:
        """InsightFace on a Frigate subject crop (bridge-only path)."""
        import cv2

        if not jpeg:
            return []
        if not (hasattr(self.recognizer, "is_loaded") and self.recognizer.is_loaded):
            return []
        arr = np.frombuffer(jpeg, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return []
        events: list[dict[str, Any]] = []
        faces = self.recognizer.detect_faces(frame)
        ts = datetime.now(timezone.utc).isoformat()
        for face in faces:
            emb = face.get("embedding")
            if emb is None:
                continue
            match = self._match_embedding(emb)
            meta_base = {
                "bbox": face.get("bbox"),
                "confidence": face.get("confidence"),
                "detection_method": "insightface_on_frigate_crop",
            }
            events.append({
                "event_type": "face_detected",
                "timestamp": ts,
                "metadata": dict(meta_base),
            })
            if match:
                events.append({
                    "event_type": "face_watchlist_match",
                    "timestamp": ts,
                    "metadata": {
                        **meta_base,
                        "label": match.get("label"),
                        "identifier": match.get("identifier"),
                        "confidence": match.get("score"),
                        "embedding_score": match.get("score"),
                    },
                })
            else:
                events.append({
                    "event_type": "face_unknown",
                    "timestamp": ts,
                    "metadata": dict(meta_base),
                })
            dump_dir = str(os.environ.get("VLM_FACE_DUMP_DIR") or "").strip()
            if dump_dir:
                try:
                    from pathlib import Path
                    Path(dump_dir).mkdir(parents=True, exist_ok=True)
                    (Path(dump_dir) / f"embedding_match_{uuid.uuid4().hex[:10]}.json").write_text(
                        json.dumps({
                            "match": match,
                            "embedding_dim": len(emb) if hasattr(emb, "__len__") else None,
                        }, indent=2),
                        encoding="utf-8",
                    )
                except OSError:
                    pass
        return events

    def _process_insightface(
        self,
        camera_id: str,
        frame: np.ndarray,
        timestamp: str,
    ) -> list[dict[str, Any]]:
        import uuid

        events: list[dict[str, Any]] = []
        faces = self.recognizer.detect_faces(frame)
        for face in faces:
            emb = face.get("embedding")
            if emb is None:
                continue
            match = self._match_embedding(emb)
            if match:
                events.append({
                    "event_id": str(uuid.uuid4()),
                    "camera_id": camera_id,
                    "event_type": "face_watchlist_match",
                    "timestamp": timestamp,
                    "severity": "critical",
                    "track_id": -1,
                    "metadata": {
                        "label": match.get("label"),
                        "identifier": match.get("identifier"),
                        "confidence": match.get("score"),
                        "bbox": face["bbox"],
                        "detection_method": "insightface",
                    },
                })
            else:
                events.append({
                    "event_id": str(uuid.uuid4()),
                    "camera_id": camera_id,
                    "event_type": "face_unknown",
                    "timestamp": timestamp,
                    "severity": "warning",
                    "track_id": -1,
                    "metadata": {
                        "bbox": face["bbox"],
                        "confidence": face.get("confidence"),
                        "detection_method": "insightface",
                    },
                })
            events.append({
                "event_id": str(uuid.uuid4()),
                "camera_id": camera_id,
                "event_type": "face_detected",
                "timestamp": timestamp,
                "severity": "info",
                "track_id": -1,
                "metadata": {
                    "bbox": face["bbox"],
                    "confidence": face.get("confidence"),
                    "detection_method": "insightface",
                },
            })
        return events

    def _enqueue_gemini_face(self, camera_id: str, frame: np.ndarray, timestamp: str) -> None:
        """Fail-closed face_detected via Gemini when InsightFace is unavailable."""
        import uuid

        import cv2

        from citevision_ai.vlm.queue import VlmJob

        now = time.monotonic()
        last = self._cooldown.get((camera_id, "face_detected"), 0.0)
        if now - last < self._cooldown_sec:
            return
        self._cooldown[(camera_id, "face_detected")] = now

        # Downscale to limit egress size (privacy: no disk write of face crops).
        h, w = frame.shape[:2]
        scale = min(1.0, 640.0 / max(w, 1))
        small = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale)))) if scale < 1.0 else frame
        ok, buf = cv2.imencode(".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            return
        jpeg = buf.tobytes()
        logger.info(
            "vlm_face_egress camera=%s bytes=%d (aggregated; no face image committed)",
            camera_id, len(jpeg),
        )
        labels = []
        for entry in self._watchlist[:8]:
            lab = entry.get("label") or entry.get("identifier") or ""
            if lab:
                labels.append(str(lab)[:40])
        extra = ""
        rule = "face_detected"
        if labels:
            rule = "face_unknown"
            extra = "watchlist_labels=" + ",".join(labels)
        skeleton = {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": rule,
            "event": rule,
            "timestamp": timestamp,
            "severity": "info" if rule == "face_detected" else "warning",
            "track_id": -1,
            "confidence": 0.0,
            "metadata": {"detection_method": "gemini_vlm"},
        }
        self._vlm_queue.try_enqueue(
            VlmJob(
                jpeg=jpeg,
                rule=rule,
                min_confidence=0.45,
                event_skeleton=skeleton,
                extra_context=extra,
            )
        )

    def _match_embedding(self, embedding: list[float]) -> dict[str, Any] | None:
        if not self._watchlist:
            return None
        vec = np.array(embedding, dtype=np.float32)
        vec = vec / (np.linalg.norm(vec) + 1e-9)
        best_score = 0.0
        best_entry = None
        for entry in self._watchlist:
            meta = entry.get("metadata", {})
            ref = meta.get("embedding")
            if not ref:
                continue
            ref_vec = np.array(ref, dtype=np.float32)
            ref_vec = ref_vec / (np.linalg.norm(ref_vec) + 1e-9)
            score = float(np.dot(vec, ref_vec))
            if score > best_score:
                best_score = score
                best_entry = entry
        if best_entry and best_score >= self.match_threshold:
            return {"label": best_entry.get("label"), "identifier": best_entry.get("identifier"), "score": best_score}
        return None
