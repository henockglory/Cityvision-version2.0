#!/usr/bin/env python3
import glob
import sys
sys.path.insert(0, "/home/gheno/citevision-v2/ai-engine/src")
from citevision_ai.evidence.service import probe_media_duration
files = sorted(glob.glob("/tmp/cv_segments/37c7d7fa-12dc-450c-8c4b-ab63ed43a819/*.mp4"))
for f in files[-3:]:
    print(f, "size", __import__("os").path.getsize(f), "dur", probe_media_duration(f))
