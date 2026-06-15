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

CLIP_DURATION_SEC = 6
RING_SECONDS = 10
RING_FPS = 5
JPEG_QUALITY = 82
