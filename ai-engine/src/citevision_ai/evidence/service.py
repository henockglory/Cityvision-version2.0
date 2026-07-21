from __future__ import annotations

import ctypes
import cv2
import gc
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from typing import Any

# Force glibc to return freed arenas to the OS after each clip encode.
# Without this, Python's numpy/ffmpeg decompression of 144 frames × 25 MB (4K)
# fragments the heap. Over hundreds of captures the RSS silently grows to 25 GB.
def _trim_malloc() -> None:
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass

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
from citevision_ai.evidence.frigate_track_binder import FrigateTrackBinder
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
    # Limit concurrent clip-encoding threads to prevent OOM.
    # Two separate semaphores prevent background-attachment threads from starving the
    # retroactive HTTP path (rules-engine evidence requests).
    #
    # Background threads (attach_evidence_async / attach_segment_evidence_async):
    #   These fire at event time, are not retried, and are best-effort.  Limit to 2.
    # Retroactive HTTP (capture_retroactive):
    #   Called repeatedly by the rules-engine (up to 8 retries); must succeed for alerts.
    #   Allow up to 4 concurrent captures — each uses ~200 MB (post inline-downscale),
    #   so 4 × 200 MB ≈ 800 MB peak, well within the 28 GB system budget.
    # Background attachment: increased to 8 so evidence is cached quickly before
    # the rules-engine first retry (8s). 8 × ~200 MB (post inline-downscale) ≈ 1.6 GB peak.
    _ENCODE_SEM = threading.BoundedSemaphore(8)
    # Retroactive HTTP: 4 concurrent, but with a SHORT timeout (5s) so the HTTP
    # call returns quickly and the rules-engine retries at 8s intervals. By then
    # the background thread has already populated the cache for most events.
    _RETRO_SEM = threading.BoundedSemaphore(4)
    _CACHE_MAX = 500                               # max entries in evidence cache
    # Speeding fires many MQTT events per track; one Frigate capture per track
    # within this window prevents encode-semaphore stampede (100 clips → drops).
    _SPEED_EVIDENCE_DEDUPE_SEC = 90.0

    def __init__(self) -> None:
        self._buffers: dict[str, FrameRingBuffer] = {}
        self._gate = EvidenceCaptureGate()
        # event_id → uploaded evidence package (populated by background capture).
        # capture_retroactive checks this first so the rules-engine gets the already-
        # uploaded package without re-capturing, eliminating semaphore contention.
        self._evidence_cache: dict[str, dict] = {}
        self._uploader = EvidenceUploader()
        self._segment_replay_cache: SegmentReplayCache | None = None
        self._frigate = FrigateEvidenceBackend()
        self._frigate_binder = FrigateTrackBinder(self._frigate_track)
        # Speeding: one Frigate capture per (camera, track) within the window.
        # Never gate the whole camera — that reuses one scene for every alert.
        self._speed_evidence_dedupe: dict[tuple[str, str], float] = {}
        self._speed_evidence_inflight: set[tuple[str, str]] = set()
        self._speed_evidence_ok: dict[tuple[str, str], float] = {}
        self._speed_evidence_last: dict[tuple[str, str], dict[str, Any]] = {}
        self._speed_evidence_lock = threading.Lock()
        # Demo loop clock: wall epoch at last demo activate / first buffer push.
        self._demo_loop_epoch: dict[str, float] = {}

    def update_frigate_bindings(
        self,
        camera_id: str,
        tracks: list[dict[str, Any]],
        *,
        frame_w: int,
        frame_h: int,
        wall_ts: float,
    ) -> None:
        self._frigate_binder.update_tracks(
            camera_id, tracks, frame_w=frame_w, frame_h=frame_h, wall_ts=wall_ts,
        )

    def inject_frigate_binding(self, camera_id: str, evt: dict[str, Any]) -> None:
        self._frigate_binder.inject_event(camera_id, evt)

    def _evidence_backend_mode(self) -> str:
        if settings.demo_mode:
            mode = (settings.demo_evidence_backend or "").strip().lower()
            if mode:
                return mode
        return (settings.evidence_backend or "ring_buffer").strip().lower()

    @property
    def _frigate_track(self):
        return self._frigate._track

    def reset_demo_activate(self, camera_id: str, previous_camera_id: str | None = None) -> None:
        """Reset Frigate timeline offsets and analytics state after demo source switch."""
        self._frigate_track.reset_demo_offset(camera_id)
        self._frigate_binder.clear_camera(camera_id)
        self._demo_loop_epoch[camera_id] = time.time()
        if previous_camera_id and previous_camera_id != camera_id:
            self._frigate_track.reset_demo_offset(previous_camera_id)
            self._frigate_binder.clear_camera(previous_camera_id)
            self._demo_loop_epoch.pop(previous_camera_id, None)

    # Cabin-camera event types: Frigate only tracks vehicles/persons passing a scene,
    # not driver-cabin close-ups. Attempting Frigate downloads for these event types
    # always fails with IncompleteRead (Frigate returns a corrupt/empty clip), and each
    # failed attempt holds its partial bytes in memory — causing multi-GB OOM when
    # many events are processed concurrently. Skip Frigate entirely for cabin events.
    _CABIN_EVENT_TYPES: frozenset[str] = frozenset({
        "seatbelt_violation",
        "seatbelt",
        "phone_use_violation",
        "phone_driving",
        "driver_phone",
        "driver_cabin",
    })

    def _try_frigate_capture(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        policy: dict[str, Any],
        images_spec: list[dict[str, Any]],
        return_upload: bool,
        *,
        live_frame=None,
        frame_ts: float | None = None,
    ) -> dict[str, Any] | None:
        mode = self._evidence_backend_mode()
        if mode not in ("frigate", "hybrid", "strict_frigate") or not self._frigate_track.enabled():
            return None
        # Skip Frigate for cabin events — see _CABIN_EVENT_TYPES docstring.
        event_type = str(evt.get("event_type") or "")
        if event_type in self._CABIN_EVENT_TYPES:
            return None
        try:
            fg = self._frigate_track.capture(
                policy, evt, org_id=org_id, camera_id=camera_id,
            )
        except Exception as exc:
            # Network/decode errors from Frigate are non-fatal in hybrid mode —
            # fall through to the ring-buffer path so the alert is never lost.
            logger.warning(
                "frigate capture exception camera=%s event=%s: %s",
                camera_id[:8], evt.get("event_id", "?"), exc,
            )
            if mode == "hybrid":
                return None
            return self._mark_frigate_failed(evt, return_upload)
        if not fg:
            return None if mode == "hybrid" else self._mark_frigate_failed(evt, return_upload)
        # Sprint 1 — structured missing (Décision 2): never upload fabricated assets.
        if str(fg.get("status") or "") == "missing" or str(
            (fg.get("meta") or {}).get("evidence_status") or ""
        ) == "missing":
            reason = str((fg.get("meta") or {}).get("abort_reason") or "missing")
            evt["evidence_status"] = "missing"
            evt["evidence_abort_reason"] = reason
            meta = fg.get("meta") if isinstance(fg.get("meta"), dict) else {}
            if meta:
                evt.setdefault("evidence_meta", meta)
            logger.info(
                "frigate capture missing camera=%s event=%s reason=%s",
                camera_id[:8], evt.get("event_id", "?"), reason,
            )
            if return_upload:
                return {"evidence_status": "missing", "abort_reason": reason, "meta": meta}
            return None
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
        extra_frames = captured.get("extra_images") or []
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
            plate_jpeg=plate_jpeg, extra_frames=extra_frames,
        )
        if not uploaded:
            uploaded = self._uploader.upload(
                org_id, camera_id, event_id, scene, subject, clip_bytes, meta,
                plate_jpeg=plate_jpeg, extra_frames=extra_frames,
            )
        if uploaded:
            evt["evidence"] = uploaded
            if pkg := uploaded.get("package"):
                evt["package"] = pkg
            evt["evidence_status"] = status
            uploaded["evidence_status"] = status
            if meta.get("capture_source") == "frigate_track" and meta.get("bbox"):
                evt["bbox"] = meta["bbox"]
                evt["bbox_source"] = meta.get("bbox_source") or "frigate_mqtt"
            if meta.get("plate_number"):
                evt["plate_number"] = meta["plate_number"]
            if meta.get("plate_confidence") is not None:
                evt["plate_confidence"] = meta["plate_confidence"]
            if event_id:
                if len(self._evidence_cache) >= self._CACHE_MAX:
                    try:
                        oldest = next(iter(self._evidence_cache))
                        del self._evidence_cache[oldest]
                    except StopIteration:
                        pass
                self._evidence_cache[event_id] = uploaded
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

    def _allows_ring_buffer_fallback(self, evt: dict[str, Any]) -> bool:
        """Ring-buffer allowed for hybrid/legacy, or cabin events in strict demo.

        Road rules (red_light / speeding) are fail-closed Frigate in strict_frigate:
        never silently ship demo_ring_buffer as a complete proof.
        """
        mode = self._evidence_backend_mode()
        if mode in ("ring_buffer", "hybrid", ""):
            return True
        et = str(evt.get("event_type") or "")
        if mode == "strict_frigate":
            if et in self._CABIN_EVENT_TYPES:
                return True
        return False

    def _demo_loop_meta(self, camera_id: str, bbox_ts: float | None) -> dict[str, Any]:
        """Position in the looping MP4 relative to last demo activate / first push."""
        loop_sec = float(getattr(settings, "demo_red_light_loop_sec", 352.52) or 352.52)
        epoch = self._demo_loop_epoch.get(camera_id)
        if epoch is None:
            epoch = time.time()
            self._demo_loop_epoch[camera_id] = epoch
        anchor = float(bbox_ts) if isinstance(bbox_ts, (int, float)) else time.time()
        # Wall-clock demo timeline: position = elapsed since epoch mod loop.
        pos = (anchor - epoch) % loop_sec if loop_sec > 0 else 0.0
        if pos < 0:
            pos += loop_sec
        return {
            "demo_loop_duration_sec": round(loop_sec, 3),
            "demo_loop_epoch": epoch,
            "demo_loop_position_sec": round(float(pos), 3),
        }

    def _ring_buffer_active(self) -> bool:
        mode = self._evidence_backend_mode()
        # strict_frigate keeps the buffer warm for cabin-only fallback (seatbelt/phone).
        if mode == "strict_frigate":
            return True
        return mode in ("ring_buffer", "hybrid", "")

    def _aligned_buffer_frame(self, camera_id: str, evt: dict[str, Any]):
        bbox_ts = evt.get("bbox_ts")
        buf = self._buffers.get(camera_id)
        if buf is not None and isinstance(bbox_ts, (int, float)):
            return buf.get_frame_at_ts(float(bbox_ts))
        return None

    def push_frame(self, camera_id: str, frame) -> None:
        if not self._ring_buffer_active():
            return
        buf = self._buffers.get(camera_id)
        if buf is None:
            buf = FrameRingBuffer(max_seconds=RING_SECONDS, fps=RING_FPS, jpeg_quality=JPEG_QUALITY)
            self._buffers[camera_id] = buf
        buf.maybe_push(frame)

    def _is_speeding_event(self, evt: dict[str, Any]) -> bool:
        return str(evt.get("event_type") or "") == "speeding"

    def _speed_track_key(self, camera_id: str, evt: dict[str, Any]) -> tuple[str, str] | None:
        """Stable per-track key; None when track_id missing (no camera-wide gate)."""
        track_id = evt.get("track_id")
        if track_id is None or track_id == "":
            return None
        return (camera_id, str(track_id))

    def _purge_speed_dedupe(self, now: float) -> None:
        expired = [k for k, ts in self._speed_evidence_dedupe.items() if now - ts > self._SPEED_EVIDENCE_DEDUPE_SEC]
        for k in expired:
            del self._speed_evidence_dedupe[k]
        expired_ok = [k for k, ts in self._speed_evidence_ok.items() if now - ts > self._SPEED_EVIDENCE_DEDUPE_SEC]
        for k in expired_ok:
            del self._speed_evidence_ok[k]

    def _should_skip_speed_evidence(self, camera_id: str, evt: dict[str, Any]) -> bool:
        """True when this track already has an in-flight or recent successful capture."""
        if not self._is_speeding_event(evt):
            return False
        key = self._speed_track_key(camera_id, evt)
        if key is None:
            return False
        now = time.time()
        with self._speed_evidence_lock:
            self._purge_speed_dedupe(now)
            if key in self._speed_evidence_ok or key in self._speed_evidence_inflight:
                return True
            prev = self._speed_evidence_dedupe.get(key)
            return prev is not None and now - prev < self._SPEED_EVIDENCE_DEDUPE_SEC

    def _begin_speed_evidence(self, camera_id: str, evt: dict[str, Any]) -> bool:
        """Reserve a speeding capture slot for this track. False ⇒ caller must skip."""
        if not self._is_speeding_event(evt):
            return True
        key = self._speed_track_key(camera_id, evt)
        # No track_id → allow capture (cannot safely dedupe); avoid camera-wide lock.
        if key is None:
            return True
        now = time.time()
        with self._speed_evidence_lock:
            self._purge_speed_dedupe(now)
            if key in self._speed_evidence_ok or key in self._speed_evidence_inflight:
                return False
            prev = self._speed_evidence_dedupe.get(key)
            if prev is not None and now - prev < self._SPEED_EVIDENCE_DEDUPE_SEC:
                return False
            self._speed_evidence_inflight.add(key)
            return True

    def _finish_speed_evidence(
        self,
        camera_id: str,
        evt: dict[str, Any],
        *,
        success: bool,
        uploaded: dict[str, Any] | None = None,
    ) -> None:
        if not self._is_speeding_event(evt):
            return
        key = self._speed_track_key(camera_id, evt)
        with self._speed_evidence_lock:
            if key is not None:
                self._speed_evidence_inflight.discard(key)
                if success:
                    self._speed_evidence_ok[key] = time.time()
                    self._speed_evidence_dedupe[key] = time.time()
                    if uploaded:
                        self._speed_evidence_last[key] = uploaded

    def _reuse_speed_evidence(self, camera_id: str, evt: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Return last good package for THIS track only (never another vehicle's scene)."""
        key = self._speed_track_key(camera_id, evt or {})
        if key is None:
            return None
        deadline = time.time() + 20.0
        while time.time() < deadline:
            with self._speed_evidence_lock:
                last = self._speed_evidence_last.get(key)
                inflight = key in self._speed_evidence_inflight
            if last is not None:
                logger.info(
                    "speed evidence dedupe reuse camera=%s track=%s",
                    camera_id[:8], key[1],
                )
                return last
            if not inflight:
                return None
            time.sleep(0.4)
        with self._speed_evidence_lock:
            return self._speed_evidence_last.get(key)

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
        if not force and not self._begin_speed_evidence(camera_id, evt):
            logger.info(
                "speed evidence dedupe skip camera=%s track=%s event=%s",
                camera_id[:8], evt.get("track_id"), str(evt.get("event_id") or "")[:8],
            )
            return
        speed_slot = self._is_speeding_event(evt) and not force
        try:
            if policy is None:
                if force:
                    policy = default_evidence_policy()
                else:
                    policy = self._gate.match_policy(camera_id, evt)
            if policy is None:
                if speed_slot:
                    self._finish_speed_evidence(camera_id, evt, success=False)
                return
            if async_upload:
                self.attach_evidence_async(
                    camera_id, org_id, evt, frame, policy=policy, frame_ts=frame_ts,
                    speed_slot=speed_slot,
                )
                return
            try:
                self._capture_and_attach(camera_id, org_id, evt, frame, policy, frame_ts=frame_ts)
                if speed_slot:
                    ok = str(evt.get("evidence_status") or "") in ("complete", "partial")
                    self._finish_speed_evidence(
                        camera_id, evt, success=ok, uploaded=evt.get("evidence") if ok else None,
                    )
            except Exception:
                if speed_slot:
                    self._finish_speed_evidence(camera_id, evt, success=False)
                raise
        except Exception:
            if speed_slot:
                self._finish_speed_evidence(camera_id, evt, success=False)
            raise

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
        speed_slot: bool = False,
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
            acquired = self._ENCODE_SEM.acquire(blocking=True, timeout=120)
            if not acquired:
                logger.warning(
                    "evidence semaphore timeout — dropping capture camera=%s event=%s",
                    camera_id[:8], evt.get("event_id", ""),
                )
                if speed_slot:
                    self._finish_speed_evidence(camera_id, evt, success=False)
                return
            try:
                self._capture_and_attach(
                    camera_id, org_id, evt, resolved_frame, policy,
                    frame_ts=frame_ts, resolved=True, bbox_quality_ok=quality_ok,
                )
                if speed_slot:
                    ok = str(evt.get("evidence_status") or "") in ("complete", "partial")
                    self._finish_speed_evidence(
                        camera_id, evt, success=ok, uploaded=evt.get("evidence") if ok else None,
                    )
            except Exception:
                logger.exception(
                    "async evidence failed camera=%s event=%s",
                    camera_id,
                    evt.get("event_id"),
                )
                if speed_slot:
                    self._finish_speed_evidence(camera_id, evt, success=False)
            finally:
                self._ENCODE_SEM.release()
                gc.collect()
                _trim_malloc()

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
            acquired = self._ENCODE_SEM.acquire(blocking=True, timeout=120)
            if not acquired:
                logger.warning(
                    "segment evidence semaphore timeout — dropping capture camera=%s event=%s",
                    camera_id[:8], evt.get("event_id", ""),
                )
                return
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
            finally:
                self._ENCODE_SEM.release()
                gc.collect()
                _trim_malloc()

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
        # Speeding: one Frigate attempt per track — rules-engine storms
        # /evidence/capture for every pending event and must not stampede Frigate.
        speed_slot = False
        if self._is_speeding_event(evt):
            if not self._begin_speed_evidence(camera_id, evt):
                reused = self._reuse_speed_evidence(camera_id, evt)
                if reused is not None:
                    return reused
                logger.info(
                    "speed evidence dedupe skip (retro) camera=%s track=%s event=%s",
                    camera_id[:8], evt.get("track_id"), str(evt.get("event_id") or "")[:8],
                )
                return None
            speed_slot = True
        # Use the dedicated retroactive semaphore (_RETRO_SEM, limit=4) so these HTTP
        # requests don't compete with the background attachment threads (_ENCODE_SEM,
        # limit=2).  Without separation, 100 concurrent events saturate both pools and
        # the majority of retries time-out before getting a slot.
        #
        # CRITICAL: if the semaphore is not acquired within the timeout, return None
        # immediately — do NOT fall through to _capture_retroactive_inner without the
        # semaphore, which would re-introduce unbounded memory usage.
        # Short timeout: if the 4 slots are busy, return None quickly so the
        # rules-engine retries after 8s.  By then the background thread has likely
        # populated the evidence cache, turning the next retry into a cache hit.
        acquired = self._RETRO_SEM.acquire(blocking=True, timeout=5)
        if not acquired:
            logger.info(
                "retroactive semaphore busy — deferring camera=%s event=%s",
                camera_id[:8], str(evt.get("event_id") or "")[:8],
            )
            if speed_slot:
                self._finish_speed_evidence(camera_id, evt, success=False)
            return None
        try:
            uploaded = self._capture_retroactive_inner(camera_id, org_id, evt, policy)
            if speed_slot:
                ok = bool(uploaded) and str(
                    (uploaded or {}).get("evidence_status")
                    or evt.get("evidence_status")
                    or ""
                ) in ("complete", "partial")
                # Also accept packages with frigate_track capture_source.
                if not ok and isinstance(uploaded, dict):
                    pkg = uploaded.get("package") or {}
                    meta = pkg.get("metadata") if isinstance(pkg, dict) else {}
                    if isinstance(meta, dict) and meta.get("capture_source") == "frigate_track":
                        ok = True
                self._finish_speed_evidence(
                    camera_id, evt, success=ok, uploaded=uploaded if ok else None,
                )
            return uploaded
        except Exception:
            if speed_slot:
                self._finish_speed_evidence(camera_id, evt, success=False)
            raise
        finally:
            self._RETRO_SEM.release()
            gc.collect()
            _trim_malloc()

    def _capture_retroactive_inner(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        # Fast path: return the package already captured by the background thread.
        # This avoids re-decompressing the ring buffer and re-uploading — which is
        # the main cause of semaphore saturation when 100+ events fire simultaneously.
        event_id = str(evt.get("event_id") or "")
        if event_id and event_id in self._evidence_cache:
            logger.debug("retroactive evidence cache hit event=%s", event_id[:8])
            return self._evidence_cache[event_id]
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
        pol = policy or default_evidence_policy()
        images_spec = pol.get("images") or default_evidence_policy()["images"]
        if self._evidence_backend_mode() in ("frigate", "hybrid", "strict_frigate") and self._frigate_track.enabled():
            fg = self._try_frigate_capture(
                camera_id, org_id, evt, pol, images_spec, return_upload=True,
            )
            if fg is not None:
                return fg
            if self._evidence_backend_mode() in ("frigate", "strict_frigate"):
                if not (
                    self._evidence_backend_mode() == "strict_frigate"
                    and self._allows_ring_buffer_fallback(evt)
                ):
                    return self._mark_frigate_failed(evt, return_upload=True)
        if not self._allows_ring_buffer_fallback(evt):
            return self._mark_frigate_failed(evt, return_upload=True)
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
        no_clip: bool = False,
    ) -> dict[str, Any] | None:
        clip_sec = float(policy.get("clip_seconds") or CLIP_DURATION_SEC)
        event_id = str(evt.get("event_id", ""))
        images_spec = policy.get("images") or default_evidence_policy()["images"]
        event_type = str(evt.get("event_type") or evt.get("event") or "")

        # Road rules: Frigate-only in strict demo — no early ring freeze/fallback that
        # used to ship demo_ring_buffer + emission_track bbox as "complete".
        if not no_clip:
            frigate_upload = self._try_frigate_capture(
                camera_id, org_id, evt, policy, images_spec, return_upload,
                live_frame=frame, frame_ts=frame_ts,
            )
            if frigate_upload is not None:
                return frigate_upload
            if self._evidence_backend_mode() in ("frigate", "strict_frigate"):
                if not (
                    self._evidence_backend_mode() == "strict_frigate"
                    and self._allows_ring_buffer_fallback(evt)
                ):
                    return self._mark_frigate_failed(evt, return_upload)
        if not self._allows_ring_buffer_fallback(evt):
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
        if buf and not no_clip:
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
        # Plate is identification-only (Tâche 4) — do not fail violation completeness.
        if not bbox_quality_ok:
            complete = False
        if subject is not None and not subject_quality_ok:
            complete = False
        status = "complete" if complete else "partial"
        capture_source = (
            "demo_ring_buffer"
            if event_type == "red_light_violation" and settings.demo_relaxed_evidence()
            else "live"
        )
        meta = {
            "bbox": norm_bbox,
            "bbox_ts": evt.get("bbox_ts"),
            "bbox_source": evt.get("bbox_source"),
            "bbox_quality_ok": bbox_quality_ok,
            "subject_texture": round(subject_texture, 1) if subject_texture is not None else None,
            "subject_quality_ok": subject_quality_ok,
            "capture_frame_ts": frame_ts,
            "capture_source": capture_source,
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
        if capture_source == "demo_ring_buffer":
            meta.update(self._demo_loop_meta(camera_id, evt.get("bbox_ts")))
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
            # Cache the result so capture_retroactive can return it instantly
            # when the rules-engine requests evidence for the same event.
            if event_id:
                if len(self._evidence_cache) >= self._CACHE_MAX:
                    try:
                        oldest = next(iter(self._evidence_cache))
                        del self._evidence_cache[oldest]
                    except StopIteration:
                        pass
                self._evidence_cache[event_id] = uploaded
        else:
            evt["evidence_status"] = "failed"
        if return_upload:
            return uploaded
        return None

    def _export_demo_ring_capture(
        self,
        camera_id: str,
        evt: dict[str, Any],
        frame,
        policy: dict[str, Any],
        images_spec: list[dict[str, Any]],
        *,
        frame_ts: float | None,
        resolved: bool,
        bbox_quality_ok: bool,
    ) -> dict[str, Any] | None:
        """Freeze ring-buffer scene/subject/clip immediately (before Frigate waits)."""
        try:
            if resolved:
                capture_frame = frame
            else:
                capture_frame, bbox_quality_ok = self.resolve_aligned_frame(
                    camera_id, evt, frame, frame_ts,
                )
            if capture_frame is None:
                return None
            clip_sec = float(policy.get("clip_seconds") or CLIP_DURATION_SEC)
            raw_bbox = bbox_from_event(evt)
            draw_bbox = policy.get("draw_bbox", True) is not False
            fh, fw = capture_frame.shape[:2]
            norm_bbox = normalize_bbox(raw_bbox, fw, fh) if raw_bbox else None
            scene, subject, extras = capture_images_from_policy(
                capture_frame, norm_bbox, images_spec, JPEG_QUALITY, draw_bbox=draw_bbox,
            )
            subject_texture = subject_jpeg_texture(subject)
            subject_quality_ok = bool(
                subject is not None
                and subject_texture is not None
                and subject_texture >= SUBJECT_MIN_TEXTURE
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
            if not (scene and subject and clip_bytes):
                logger.info(
                    "demo_ring_buffer incomplete cam=%s scene=%s subject=%s clip=%s",
                    camera_id[:8], bool(scene), bool(subject), bool(clip_bytes),
                )
                return None
            want_plate = any(s.get("role") == "plate" for s in images_spec)
            plate_jpeg = extras[0] if extras else None
            missing_roles = ["plate"] if want_plate and not plate_jpeg else []
            status = "complete" if bbox_quality_ok and subject_quality_ok else "partial"
            meta = {
                "bbox": norm_bbox,
                "bbox_ts": evt.get("bbox_ts"),
                "bbox_source": evt.get("bbox_source"),
                "bbox_quality_ok": bbox_quality_ok,
                "subject_texture": round(subject_texture, 1) if subject_texture is not None else None,
                "subject_quality_ok": subject_quality_ok,
                "capture_frame_ts": frame_ts,
                "capture_source": "demo_ring_buffer",
                "confidence": evt.get("confidence"),
                "class_name": evt.get("class_name"),
                "zone_id": evt.get("zone_id"),
                "track_id": evt.get("track_id"),
                "event_type": evt.get("event_type") or evt.get("event"),
                "clip_duration_sec": clip_duration,
                "plate_number": evt.get("plate_number"),
                "plate_confidence": evt.get("plate_confidence"),
                "missing_roles": missing_roles,
                "evidence_status": status,
            }
            meta.update(self._demo_loop_meta(camera_id, evt.get("bbox_ts")))
            return {
                "status": status,
                "scene": scene,
                "subject": subject,
                "clip_bytes": clip_bytes,
                "plate_jpeg": plate_jpeg,
                "extra_images": [],
                "meta": meta,
            }
        except Exception as exc:
            logger.warning(
                "demo_ring_buffer export failed cam=%s: %s", camera_id[:8], exc,
            )
            return None

    def clear_camera(self, camera_id: str) -> None:
        self._buffers.pop(camera_id, None)
        self._gate.clear_camera(camera_id)

    def clear_camera_rules_only(self, camera_id: str) -> None:
        """Clear capture rules but preserve the ring buffer.

        Called when a camera is stopped so that any in-flight rules-engine evidence
        retries (which may arrive seconds after the camera stops) can still succeed.
        The ring buffer is replaced automatically when the camera restarts.
        """
        self._gate.clear_camera(camera_id)
