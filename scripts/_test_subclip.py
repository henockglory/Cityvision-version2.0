#!/usr/bin/env python3
import subprocess
import sys
sys.path.insert(0, "/home/gheno/citevision-v2/ai-engine/src")
from citevision_ai.evidence.service import extract_subclip_mp4

seg = "/tmp/cv_segments/37c7d7fa-12dc-450c-8c4b-ab63ed43a819/110-d68d0cbd.mp4"
data = extract_subclip_mp4(seg, 5.0, 6.0)
print("bytes", len(data) if data else None)
if data:
    open("/tmp/test_subclip.mp4", "wb").write(data)
    pr = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "json", "/tmp/test_subclip.mp4"],
        capture_output=True, text=True,
    )
    print(pr.stdout)
