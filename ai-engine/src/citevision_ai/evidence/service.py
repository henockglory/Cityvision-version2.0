from __future__ import annotations

import cv2
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from typing import Any

from citevision_ai.evidence.buffer import FrameRingBuffer
from citevision_ai.evidence.capture import (
    bbox_from_event,
    bbox_region_has_content,
    capture_images_from_policy,
    normalize_bbox,
    subject_jpeg_texture,
)
from citevision_ai.evidence.config import (
    CLIP_DURATION_SEC,
    FRAME_ALIGN_TOLERANCE_SEC,
    JPEG_QUALITY,
    RING_FPS,
    RING_SECONDS,
)
from citevision_ai.evidence.frigate_backend import FrigateEvidenceBackend
from citevision_ai.evidence.gate import EvidenceCaptureGate, default_evidence_policy
from citevision_ai.evidence.uploader import EvidenceUploader
from citevision_ai.config import settings
from citevision_ai.evidence.segment_align import resolve_segment_capture_frame, segment_pts_from_bbox_ts
from citevision_ai.evidence.segment_replay_cache import SegmentReplayCache

logger = logging.getLogger(__name__)

SUBJECT_MIN_TEXTURE = 50.0
_EMISSION_BBOX_SOURCES = frozenset({"emission_track", "last_known", "event_fallback"})


def probe_media_duration(path: str) -> float | None:
    """Return media duration in seconds via ffprobe, or None."""
    if not os.path.isfile(path):
        return None
    ffprobe = shutil.which("ffprobe") or "/usr/bin/ffprobe"
    if not os.path.isfile(ffprobe):
        return None
    try:
        proc = subprocess.run(
            [
                ffprobe, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", path,
            ],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if proc.returncode != 0:
            return None
        val = float(proc.stdout.strip())
        return val if val > 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def extract_subclip_mp4(segment_path: str, center_pts: float, duration_sec: float) -> bytes | None:
    """Cut a sub-clip from a segment MP4 centred on ``center_pts`` (seconds)."""
    if not shutil.which("ffmpeg") or not os.path.isfile(segment_path):
        return None
    media_dur = probe_media_duration(segment_path)
    if media_dur is not None and media_dur > 0:
        center_pts = min(max(0.0, center_pts), max(0.0, media_dur - 0.05))
        duration_sec = min(duration_sec, media_dur)
    half = duration_sec / 2.0
    start = max(0.0, center_pts - half)
    if media_dur is not None:
        start = min(start, max(0.0, media_dur - duration_sec))
        duration_sec = min(duration_sec, max(0.1, media_dur - start))
    tmp = tempfile.mkdtemp(prefix="cv_seg_clip_")
    out_path = os.path.join(tmp, "clip.mp4")
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", segment_path,
            "-ss", f"{start:.3f}",
            "-t", f"{duration_sec:.3f}",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-preset", "veryfast",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=False)
        if result.returncode != 0:
            logger.warning("segment subclip ffmpeg failed: %s", result.stderr[-400:])
            return None
        with open(out_path, "rb") as f:
            data = f.read()
        if len(data) < 1000:
            return None
        nf = probe_frame_count(out_path)
        if nf is None or nf < 2:
            return None
        return data
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("segment subclip error: %s", exc)
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def probe_frame_count(path: str) -> int | None:
    ffprobe = shutil.which("ffprobe") or "/usr/bin/ffprobe"
    if not os.path.isfile(ffprobe):
        return None
    try:
        proc = subprocess.run(
            [
                ffprobe, "-v", "error", "-select_streams", "v:0",
                "-count_frames", "-show_entries", "stream=nb_read_frames",
                "-of", "default=noprint_wrappers=1:nokey=1", path,
            ],
            capture_output=True, text=True, timeout=20, check=False,
        )
        if proc.returncode != 0:
            return None
        return int(proc.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _parse_event_ts(evt: dict[str, Any]) -> float | None:
    event_ts = evt.get("timestamp") or evt.get("ts")
    if isinstance(event_ts, (int, float)):
        return float(event_ts)
    if isinstance(event_ts, str):
        try:
            return datetime.fromisoformat(event_ts.replace("Z", "+00:00")).timestamp()
        except ValueError:
            try:
                return float(event_ts)
            except ValueError:
                return None
    return None


class EvidenceCaptureService:
    def __init__(self) -> None:
        self._buffers: dict[str, FrameRingBuffer] = {}
        self._gate = EvidenceCaptureGate()
        self._uploader = EvidenceUploader()
        self._segment_replay_cache: SegmentReplayCache | None = None
        self._frigate = FrigateEvidenceBackend()

    def _evidence_backend_mode(self) -> str:
        return (settings.evidence_backend or "ring_buffer").strip().lower()

    def _try_frigate_capture(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        policy: dict[str, Any],
        images_spec: list[dict[str, Any]],
        return_upload: bool,
    ) -> dict[str, Any] | None:
        mode = self._evidence_backend_mode()
        if mode not in ("frigate", "hybrid") or not self._frigate.enabled():
            return None
        fg = self._frigate.capture(policy, evt, org_id=org_id, camera_id=camera_id)
        if not fg:
            return None if mode == "hybrid" else self._mark_frigate_failed(evt, return_upload)
        return self._upload_capture_result(
            org_id, camera_id, str(evt.get("event_id", "")), evt, fg, images_spec, return_upload,
        )

    def _mark_frigate_failed(
        self, evt: dict[str, Any], return_upload: bool,
    ) -> dict[str, Any] | None:
        evt["evidence_status"] = "failed"
        return None if not return_upload else {"evidence_status": "failed"}

    def _upload_capture_result(
        self,
        org_id: str,
        camera_id: str,
        event_id: str,
        evt: dict[str, Any],
        captured: dict[str, Any],
        images_spec: list[dict[str, Any]],
        return_upload: bool,
    ) -> dict[str, Any] | None:
        scene = captured.get("scene")
        subject = captured.get("subject")
        clip_bytes = captured.get("clip_bytes")
        plate_jpeg = captured.get("plate_jpeg")
        meta = dict(captured.get("meta") or {})
        image_labels: dict[str, str] = {}
        for spec in images_spec:
            role = str(spec.get("role", ""))
            label = spec.get("label")
            if role and label:
                image_labels[role] = str(label)
        meta["image_labels"] = image_labels
        status = str(meta.get("evidence_status") or captured.get("status") or "partial")
        uploaded = self._uploader.upload(
            org_id, camera_id, event_id, scene, subject, clip_bytes, meta,
            plate_jpeg=plate_jpeg,
        )
        if not uploaded:
            uploaded = self._uploader.upload(
                org_id, camera_id, event_id, scene, subject, clip_bytes, meta,
                plate_jpeg=plate_jpeg,
            )
        if uploaded:
            evt["evidence"] = uploaded
            if pkg := uploaded.get("package"):
                evt["package"] = pkg
            evt["evidence_status"] = status
            if meta.get("plate_number"):
                evt["plate_number"] = meta["plate_number"]
            if meta.get("plate_confidence") is not None:
                evt["plate_confidence"] = meta["plate_confidence"]
        else:
            evt["evidence_status"] = "failed"
            status = "failed"
        if return_upload:
            return uploaded
        return None

    def set_segment_replay_cache(self, cache: SegmentReplayCache) -> None:
        self._segment_replay_cache = cache

    def _resolve_segment_evidence_frame(
        self,
        camera_id: str,
        cycle_id: str,
        evt: dict[str, Any],
        frame,
        segment_path: str,
        capture_pts: float,
        frame_index: int,
        bbox: dict[str, Any] | None,
    ):
        width = frame.shape[1] if frame is not None and getattr(frame, "shape", None) else 1920
        height = frame.shape[0] if frame is not None and getattr(frame, "shape", None) else 1080
        norm_bbox = normalize_bbox(bbox, width, height) if bbox else None
        want_idx = evt.get("segment_bbox_frame_index")
        cache = self._segment_replay_cache
        if cache is not None and cycle_id and want_idx is not None:
            try:
                base = int(want_idx)
            except (TypeError, ValueError):
                base = None
            if base is not None:
                for idx in (base, base - 1, base + 1, base - 2, base + 2, base - 3, base + 3):
                    if idx < 0:
                        continue
                    cached = cache.get_bgr(camera_id, cycle_id, idx)
                    if cached is None:
                        continue
                    if norm_bbox and not bbox_region_has_content(cached, norm_bbox):
                        continue
                    evt["segment_bbox_frame_index"] = idx
                    return cached

        resolved = resolve_segment_capture_frame(
            frame,
            segment_path if segment_path and os.path.isfile(segment_path) else None,
            evt,
            capture_pts,
            width,
            height,
            current_frame_index=frame_index,
        )
        if resolved is not None and getattr(resolved, "size", 0):
            if norm_bbox and not bbox_region_has_content(resolved, norm_bbox):
                logger.warning(
                    "segment evidence bbox region empty cam=%s cycle=%s idx=%s pts=%.2f",
                    camera_id[:8], cycle_id, want_idx, capture_pts,
                )
            return resolved
        return frame

    def set_capture_rules(self, camera_id: str, rules: list[dict[str, Any]] | None) -> None:
        self._gate.set_rules(camera_id, rules)

    def _ring_buffer_active(self) -> bool:
        mode = self._evidence_backend_mode()
        if mode == "frigate" and self._frigate.enabled():
            return False
        return mode in ("ring_buffer", "hybrid", "")

    def push_frame(self, camera_id: str, frame) -> None:
        if not self._ring_buffer_active():
            return
        buf = self._buffers.get(camera_id)
        if buf is None:
            buf = FrameRingBuffer(max_seconds=RING_SECONDS, fps=RING_FPS, jpeg_quality=JPEG_QUALITY)
            self._buffers[camera_id] = buf
        buf.maybe_push(frame)

    def attach_evidence(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        frame,
        *,
        force: bool = False,
        policy: dict[str, Any] | None = None,
        async_upload: bool = True,
        frame_ts: float | None = None,
    ) -> None:
        if not org_id:
            return
        if policy is None:
            if force:
                policy = default_evidence_policy()
            else:
                policy = self._gate.match_policy(camera_id, evt)
        if policy is None:
            return
        if async_upload:
            self.attach_evidence_async(camera_id, org_id, evt, frame, policy=policy, frame_ts=frame_ts)
            return
        self._capture_and_attach(camera_id, org_id, evt, frame, policy, frame_ts=frame_ts)

    def resolve_aligned_frame(
        self,
        camera_id: str,
        evt: dict[str, Any],
        frame,
        frame_ts: float | None = None,
    ) -> tuple[Any, bool]:
        """Pick the capture frame; co-emission live events use the inference frame as-is."""
        bbox_src = evt.get("bbox_source")
        if bbox_src in _EMISSION_BBOX_SOURCES:
            if frame is None:
                return frame, False
            raw_bbox = bbox_from_event(evt)
            if raw_bbox is None:
                return frame, True
            fh, fw = frame.shape[:2]
            norm = normalize_bbox(raw_bbox, fw, fh)
            if not norm or bbox_region_has_content(frame, norm):
                return frame, True
            logger.warning(
                "emission bbox region empty camera=%s event=%s source=%s",
                camera_id[:8], evt.get("event_id"), bbox_src,
            )
            return frame, False

        capture_frame = self._resolve_capture_frame(camera_id, evt, frame, frame_ts)
        raw_bbox = bbox_from_event(evt)
        if raw_bbox is None or capture_frame is None:
            return capture_frame, True
        fh, fw = capture_frame.shape[:2]
        norm = normalize_bbox(raw_bbox, fw, fh)
        if not norm:
            return capture_frame, True
        if bbox_region_has_content(capture_frame, norm):
            return capture_frame, True
        bbox_ts = evt.get("bbox_ts")
        buf = self._buffers.get(camera_id)
        if buf is not None and isinstance(bbox_ts, (int, float)):
            for cand, cand_ts in buf.get_frames_near_ts(float(bbox_ts), max_frames=6):
                if bbox_region_has_content(cand, norm):
                    logger.info(
                        "evidence frame realigned camera=%s event=%s dt=%.3fs",
                        camera_id[:8], evt.get("event_id"), cand_ts - float(bbox_ts),
                    )
                    return cand, True
        logger.warning(
            "evidence bbox region empty camera=%s event=%s bbox_ts=%s",
            camera_id[:8], evt.get("event_id"), bbox_ts,
        )
        return capture_frame, False

    def attach_evidence_async(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        frame,
        *,
        policy: dict[str, Any],
        frame_ts: float | None = None,
    ) -> None:
        """Frame selection happens synchronously (ring buffer still holds the
        bbox-instant frame); crops, clip export and backend upload run in a
        background thread so ingest never blocks on ffmpeg or HTTP."""
        try:
            resolved_frame, quality_ok = self.resolve_aligned_frame(
                camera_id, evt, frame, frame_ts,
            )
        except Exception:
            logger.exception(
                "frame alignment failed camera=%s event=%s",
                camera_id, evt.get("event_id"),
            )
            resolved_frame, quality_ok = frame, False

        def _run() -> None:
            try:
                self._capture_and_attach(
                    camera_id, org_id, evt, resolved_frame, policy,
                    frame_ts=frame_ts, resolved=True, bbox_quality_ok=quality_ok,
                )
            except Exception:
                logger.exception(
                    "async evidence failed camera=%s event=%s",
                    camera_id,
                    evt.get("event_id"),
                )

        threading.Thread(
            target=_run,
            daemon=True,
            name=f"evidence-{evt.get('event_id', 'evt')}",
        ).start()

    def attach_segment_evidence_async(
        self,
        org_id: str,
        camera_id: str,
        evt: dict[str, Any],
        frame,
        segment_path: str,
        frame_pts: float,
        policy: dict[str, Any],
        *,
        cycle_id: str = "",
        frame_index: int = 0,
    ) -> None:
        def _run() -> None:
            try:
                self.capture_from_segment(
                    org_id,
                    camera_id,
                    evt,
                    frame,
                    segment_path,
                    frame_pts,
                    policy,
                    cycle_id=cycle_id,
                    frame_index=frame_index,
                )
            except Exception:
                logger.exception(
                    "segment evidence failed camera=%s event=%s",
                    camera_id,
                    evt.get("event_id"),
                )

        threading.Thread(
            target=_run,
            daemon=True,
            name=f"seg-evidence-{evt.get('event_id', 'evt')}",
        ).start()

    def capture_from_segment(
        self,
        org_id: str,
        camera_id: str,
        evt: dict[str, Any],
        frame,
        segment_path: str,
        frame_pts: float,
        policy: dict[str, Any],
        *,
        cycle_id: str = "",
        frame_index: int = 0,
    ) -> dict[str, Any] | None:
        """Evidence from the recorded segment — frame and clip are time-aligned."""
        clip_sec = float(policy.get("clip_seconds") or CLIP_DURATION_SEC)
        event_id = str(evt.get("event_id", ""))
        raw_bbox = bbox_from_event(evt)
        images_spec = policy.get("images") or default_evidence_policy()["images"]
        draw_bbox = policy.get("draw_bbox", True) is not False

        capture_pts = frame_pts
        bbox_pts = evt.get("segment_bbox_pts")
        if bbox_pts is not None:
            try:
                capture_pts = float(bbox_pts)
            except (TypeError, ValueError):
                pass
        else:
            derived = segment_pts_from_bbox_ts(evt.get("bbox_ts"), evt.get("segment_start_wall", 0.0))
            if derived is not None:
                capture_pts = derived

        capture_frame = self._resolve_segment_evidence_frame(
            camera_id,
            cycle_id,
            evt,
            frame,
            segment_path,
            capture_pts,
            frame_index,
            raw_bbox,
        )

        fh, fw = capture_frame.shape[:2]
        norm_bbox = normalize_bbox(raw_bbox, fw, fh) if raw_bbox else None
        scene, subject, extras = capture_images_from_policy(
            capture_frame, norm_bbox, images_spec, JPEG_QUALITY, draw_bbox=draw_bbox,
        )
        clip_bytes = extract_subclip_mp4(segment_path, capture_pts, clip_sec)
        if not clip_bytes:
            logger.warning(
                "segment clip extraction failed cam=%s cycle=%s pts=%.2f path=%s",
                camera_id[:8], cycle_id, capture_pts, segment_path,
            )
        media_dur = probe_media_duration(segment_path)
        effective = min(clip_sec, media_dur) if media_dur else clip_sec
        clip_duration = effective if clip_bytes else 0.0
        plate_jpeg = extras[0] if extras else None
        image_labels: dict[str, str] = {}
        for spec in images_spec:
            role = str(spec.get("role", ""))
            label = spec.get("label")
            if role and label:
                image_labels[role] = str(label)
        want_plate = any(s.get("role") == "plate" for s in images_spec)
        missing_roles: list[str] = []
        if want_plate and not plate_jpeg:
            missing_roles.append("plate")
        complete = bool(scene and subject and clip_bytes)
        if want_plate and not plate_jpeg:
            complete = False
        status = "complete" if complete else "partial"
        meta = {
            "bbox": norm_bbox,
            "bbox_ts": evt.get("bbox_ts"),
            "capture_frame_ts": capture_pts,
            "capture_source": "segment",
            "segment_cycle_id": cycle_id,
            "segment_frame_index": evt.get("segment_bbox_frame_index", frame_index),
            "segment_bbox_frame_index": evt.get("segment_bbox_frame_index"),
            "segment_frame_pts": capture_pts,
            "confidence": evt.get("confidence"),
            "class_name": evt.get("class_name"),
            "zone_id": evt.get("zone_id"),
            "track_id": evt.get("track_id"),
            "event_type": evt.get("event_type") or evt.get("event"),
            "clip_duration_sec": clip_duration,
            "plate_number": evt.get("plate_number"),
            "plate_confidence": evt.get("plate_confidence"),
            "image_labels": image_labels,
            "missing_roles": missing_roles,
            "evidence_status": status,
        }
        uploaded = self._uploader.upload(
            org_id, camera_id, event_id, scene, subject, clip_bytes, meta,
            plate_jpeg=plate_jpeg,
        )
        if not uploaded:
            uploaded = self._uploader.upload(
                org_id, camera_id, event_id, scene, subject, clip_bytes, meta,
                plate_jpeg=plate_jpeg,
            )
        if uploaded:
            evt["evidence"] = uploaded
            if pkg := uploaded.get("package"):
                evt["package"] = pkg
            evt["evidence_status"] = status
        else:
            evt["evidence_status"] = "failed"
        return uploaded

    def capture_retroactive(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        seg_path = evt.get("segment_path")
        frame_pts = evt.get("segment_frame_pts")
        if (
            isinstance(seg_path, str)
            and seg_path
            and os.path.isfile(seg_path)
            and isinstance(frame_pts, (int, float))
        ):
            pol = policy or default_evidence_policy()
            buf = self._buffers.get(camera_id)
            frame = None
            if buf:
                frame = buf.get_last_frame()
            if frame is None:
                cap = cv2.VideoCapture(seg_path)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_POS_MSEC, float(frame_pts) * 1000.0)
                    ok, frame = cap.read()
                    cap.release()
                if frame is None:
                    logger.warning("segment retro capture: no frame at pts=%s", frame_pts)
                    return None
            return self.capture_from_segment(
                org_id,
                camera_id,
                evt,
                frame,
                seg_path,
                float(frame_pts),
                pol,
                cycle_id=str(evt.get("segment_cycle_id") or ""),
                frame_index=int(evt.get("segment_frame_index") or 0),
            )
        if camera_id in settings.parsed_segment_mode_camera_ids():
            logger.warning(
                "segment retro capture unavailable camera=%s (segment file gone)",
                camera_id,
            )
            return None
        buf = self._buffers.get(camera_id)
        bbox_ts = evt.get("bbox_ts")
        event_ts = _parse_event_ts(evt)
        lookup_ts: float | None = None
        if isinstance(bbox_ts, (int, float)):
            lookup_ts = float(bbox_ts)
        elif event_ts is not None:
            lookup_ts = float(event_ts)
        else:
            lookup_ts = time.time()
        frame = None
        frame_ts: float | None = None
        if buf and lookup_ts is not None:
            frame = buf.get_frame_at_ts(lookup_ts)
            if frame is not None:
                frame_ts = lookup_ts
        if frame is None and buf:
            frame = buf.get_last_frame()
        if frame is None:
            logger.warning("retro capture unavailable camera=%s (no buffer frame)", camera_id)
            return None
        pol = policy or default_evidence_policy()
        return self._capture_and_attach(
            camera_id, org_id, evt, frame, pol, return_upload=True, frame_ts=frame_ts,
        )

    def _resolve_capture_frame(
        self,
        camera_id: str,
        evt: dict[str, Any],
        frame,
        frame_ts: float | None = None,
    ):
        """Pick the frame that actually matches ``evt["bbox"]`` in time.

        Priority:
        1. The live frame already in hand, when its wall-clock timestamp is close
           to the bbox's source-frame timestamp (``bbox_ts``) — perfect alignment,
           no ring-buffer lookup needed. This is the common case since the pipeline
           prefers the current frame's bbox before falling back to history.
        2. A ring-buffer frame looked up by ``bbox_ts`` (not the event-emission
           timestamp, which can be hundreds of ms later than the bbox itself and
           land on a frame where the vehicle has already moved off-crop).
        3. Legacy fallback: ring buffer by event-emission timestamp, then the
           last known frame, then the frame passed in.
        """
        bbox_ts = evt.get("bbox_ts")
        has_bbox_ts = isinstance(bbox_ts, (int, float))
        if has_bbox_ts and frame_ts is not None and abs(float(bbox_ts) - float(frame_ts)) <= FRAME_ALIGN_TOLERANCE_SEC:
            return frame
        buf = self._buffers.get(camera_id)
        if has_bbox_ts and buf:
            buffered = buf.get_frame_at_ts(float(bbox_ts))
            if buffered is not None:
                return buffered
        event_ts = _parse_event_ts(evt)
        if buf and event_ts is not None:
            buffered = buf.get_frame_at_ts(float(event_ts))
            if buffered is not None:
                return buffered
            last = buf.get_last_frame()
            if last is not None:
                return last
        return frame

    def _capture_and_attach(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        frame,
        policy: dict[str, Any],
        return_upload: bool = False,
        frame_ts: float | None = None,
        resolved: bool = False,
        bbox_quality_ok: bool = True,
    ) -> dict[str, Any] | None:
        clip_sec = float(policy.get("clip_seconds") or CLIP_DURATION_SEC)
        event_id = str(evt.get("event_id", ""))
        images_spec = policy.get("images") or default_evidence_policy()["images"]
        frigate_upload = self._try_frigate_capture(
            camera_id, org_id, evt, policy, images_spec, return_upload,
        )
        if frigate_upload is not None:
            return frigate_upload
        if self._evidence_backend_mode() == "frigate":
            return self._mark_frigate_failed(evt, return_upload)
        if resolved:
            capture_frame = frame
        else:
            capture_frame, bbox_quality_ok = self.resolve_aligned_frame(
                camera_id, evt, frame, frame_ts,
            )
        raw_bbox = bbox_from_event(evt)
        images_spec = policy.get("images") or default_evidence_policy()["images"]
        draw_bbox = policy.get("draw_bbox", True) is not False
        fh, fw = capture_frame.shape[:2]
        norm_bbox = normalize_bbox(raw_bbox, fw, fh) if raw_bbox else None
        scene, subject, extras = capture_images_from_policy(
            capture_frame, norm_bbox, images_spec, JPEG_QUALITY, draw_bbox=draw_bbox,
        )
        subject_texture = subject_jpeg_texture(subject)
        if subject is None:
            subject_quality_ok = False
        else:
            subject_quality_ok = (
                subject_texture is not None and subject_texture >= SUBJECT_MIN_TEXTURE
            )
        if subject is not None and not subject_quality_ok:
            bbox_quality_ok = False
        buf = self._buffers.get(camera_id)
        clip_bytes: bytes | None = None
        clip_duration = 0.0
        if buf:
            if evt.get("bbox_source") in _EMISSION_BBOX_SOURCES and frame_ts is not None:
                anchor_ts = float(frame_ts)
            else:
                anchor_ts = evt.get("bbox_ts")
                if not isinstance(anchor_ts, (int, float)):
                    anchor_ts = _parse_event_ts(evt)
            exported = buf.export_clip_mp4(
                clip_sec,
                RING_FPS,
                center_ts=float(anchor_ts) if anchor_ts is not None else None,
            )
            if exported:
                clip_bytes = exported.data
                clip_duration = exported.duration_sec
        plate_jpeg = extras[0] if extras else None
        image_labels: dict[str, str] = {}
        for spec in images_spec:
            role = str(spec.get("role", ""))
            label = spec.get("label")
            if role and label:
                image_labels[role] = str(label)
        want_plate = any(s.get("role") == "plate" for s in images_spec)
        missing_roles: list[str] = []
        if want_plate and not plate_jpeg:
            missing_roles.append("plate")
        complete = bool(scene and subject and clip_bytes)
        if want_plate and not plate_jpeg:
            complete = False
        if not bbox_quality_ok:
            complete = False
        if subject is not None and not subject_quality_ok:
            complete = False
        status = "complete" if complete else "partial"
        meta = {
            "bbox": norm_bbox,
            "bbox_ts": evt.get("bbox_ts"),
            "bbox_source": evt.get("bbox_source"),
            "bbox_quality_ok": bbox_quality_ok,
            "subject_texture": round(subject_texture, 1) if subject_texture is not None else None,
            "subject_quality_ok": subject_quality_ok,
            "capture_frame_ts": frame_ts,
            "capture_source": "live",
            "confidence": evt.get("confidence"),
            "class_name": evt.get("class_name"),
            "zone_id": evt.get("zone_id"),
            "track_id": evt.get("track_id"),
            "event_type": evt.get("event_type") or evt.get("event"),
            "clip_duration_sec": clip_duration,
            "plate_number": evt.get("plate_number"),
            "plate_confidence": evt.get("plate_confidence"),
            "image_labels": image_labels,
            "missing_roles": missing_roles,
            "evidence_status": status,
        }
        uploaded = self._uploader.upload(
            org_id, camera_id, event_id, scene, subject, clip_bytes, meta,
            plate_jpeg=plate_jpeg,
        )
        if not uploaded:
            uploaded = self._uploader.upload(
                org_id, camera_id, event_id, scene, subject, clip_bytes, meta,
                plate_jpeg=plate_jpeg,
            )
        if uploaded:
            evt["evidence"] = uploaded
            if pkg := uploaded.get("package"):
                evt["package"] = pkg
            evt["evidence_status"] = status
        else:
            evt["evidence_status"] = "failed"
        if return_upload:
            return uploaded
        return None

    def clear_camera(self, camera_id: str) -> None:
        self._buffers.pop(camera_id, None)
        self._gate.clear_camera(camera_id)
