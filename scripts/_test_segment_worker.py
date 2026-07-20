#!/usr/bin/env python3
from citevision_ai.config import settings
from citevision_ai.ingest.rtsp_worker import WorkerManager, SegmentCycleWorker

cam = "37c7d7fa-12dc-450c-8c4b-ab63ed43a819"
print("in set", cam in settings.parsed_segment_mode_camera_ids())

def pf(*a, **k):
    pass

wm = WorkerManager(pf, begin_replay_fn=lambda c: None)
st = wm.start_camera(cam, rtsp_url="rtsp://test", ai_fps=8)
print(st)
print(type(wm._workers[cam]).__name__)
wm.stop_camera(cam)
