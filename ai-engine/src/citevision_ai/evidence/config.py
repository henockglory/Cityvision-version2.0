"""Event types that trigger media evidence capture."""

EVIDENCE_WORTHY_TYPES = frozenset({
    "zone_presence",
    "zone_enter",
    "zone_exit",
    "loitering",
    "line_cross",
    "face_detected",
    "plate_detected",
    "zone_absence",
    "intrusion",
    "running",
    "crowd_gathering",
})

CLIP_DURATION_SEC = 5
RING_SECONDS = 8
# 6 fps (was 3): halves the worst-case gap between a bbox's source frame and the
# ring-buffer frame used for evidence when the live frame isn't directly reusable
# (e.g. finalized on track loss, a few hundred ms after the bbox was observed).
RING_FPS = 6
JPEG_QUALITY = 72

# Max drift (seconds) between a bbox's source-frame timestamp and the live frame
# already in hand before we fall back to a ring-buffer lookup by that timestamp.
FRAME_ALIGN_TOLERANCE_SEC = 0.15
