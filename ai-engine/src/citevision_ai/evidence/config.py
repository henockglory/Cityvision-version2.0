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
RING_SECONDS = 12
# 12 fps ring buffer: ~144 frames of history — enough for a smooth 6 s clip even
# when inference runs at 8 Hz. Fed directly from the RTSP read loop, not inference.
RING_FPS = 12
JPEG_QUALITY = 80

# Max drift (seconds) between a bbox's source-frame timestamp and the live frame
# already in hand before we fall back to a ring-buffer lookup by that timestamp.
FRAME_ALIGN_TOLERANCE_SEC = 0.15
