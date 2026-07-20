#!/usr/bin/env python3
"""Simulate capture_from_segment like runtime EOF."""
import os
import sys
import tempfile
import subprocess

sys.path.insert(0, "/home/gheno/citevision-v2/ai-engine/src")
import cv2
import numpy as np
from citevision_ai.evidence.service import EvidenceCaptureService, extract_subclip_mp4, probe_media_duration

# Build a segment like worker export
tmp = tempfile.mkdtemp()
seg = os.path.join(tmp, "seg.mp4")
writer = cv2.VideoWriter(seg, cv2.VideoWriter_fourcc(*"mp4v"), 12, (320, 240))
for i in range(84):
    writer.write(np.full((240, 320, 3), (i % 255, 20, 20), dtype=np.uint8))
writer.release()

# Re-encode like worker ffmpeg export
out = os.path.join(tmp, "seg_h264.mp4")
subprocess.run([
    "ffmpeg", "-y", "-framerate", "12", "-i", os.path.join(tmp, "frame_%05d.jpg"),
    "-c:v", "libx264", "-pix_fmt", "yuv420p", out,
], check=False, capture_output=True)
# use jpeg export like worker
frames_dir = os.path.join(tmp, "frames")
os.makedirs(frames_dir, exist_ok=True)
cap = cv2.VideoCapture(seg)
idx = 0
while True:
    ok, f = cap.read()
    if not ok:
        break
    cv2.imwrite(os.path.join(frames_dir, f"f_{idx:05d}.jpg"), f)
    idx += 1
cap.release()
h264 = os.path.join(tmp, "worker.mp4")
subprocess.run([
    "ffmpeg", "-y", "-framerate", "12",
    "-i", os.path.join(frames_dir, "f_%05d.jpg"),
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
    "-preset", "veryfast", h264,
], check=False)
dur = probe_media_duration(h264)
print("segment dur", dur)
for pts in (dur or 10, 10.0):
    clip = extract_subclip_mp4(h264, pts, 6.0)
    print("pts", pts, "clip bytes", len(clip) if clip else None)

svc = EvidenceCaptureService()
evt = {"event_id": "test-evt", "event_type": "speeding", "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}}
cap = cv2.VideoCapture(h264)
cap.set(cv2.CAP_PROP_POS_MSEC, max(0, (dur or 6) - 0.1) * 1000)
ok, frame = cap.read()
cap.release()
pol = {"clip_seconds": 6, "images": [{"role": "scene"}, {"role": "subject"}]}
# dry-run subclip only (no upload)
clip = extract_subclip_mp4(h264, dur or 10, 6.0)
print("eof clip", len(clip) if clip else None)
