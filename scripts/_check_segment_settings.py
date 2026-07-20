#!/usr/bin/env python3
import sys
sys.path.insert(0, "/home/gheno/citevision-v2/ai-engine/src")
from citevision_ai.config import settings
print("segment_mode_camera_ids:", repr(settings.segment_mode_camera_ids))
print("parsed:", settings.parsed_segment_mode_camera_ids())
