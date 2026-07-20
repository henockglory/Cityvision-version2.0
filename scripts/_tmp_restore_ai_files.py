from pathlib import Path

win = Path("/mnt/c/Users/gheno/citevision/ai-engine/src")
dst = Path("/home/gheno/citevision-v2/ai-engine/src")
files = [
    "citevision_ai/pipeline.py",
    "citevision_ai/road_enforcement/traffic_light.py",
    "citevision_ai/evidence/frigate_track_evidence.py",
]
for rel in files:
    t = (win / rel).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    (dst / rel).write_text(t, encoding="utf-8", newline="\n")
    print("ok", rel)

text = (dst / "citevision_ai/pipeline.py").read_text(encoding="utf-8")
assert "AbandonedObjectDetector" in text, "pipeline truncated"
text = (dst / "citevision_ai/evidence/frigate_track_evidence.py").read_text(encoding="utf-8")
assert "import urllib.error" in text, "urllib truncated"
print("restore_ok")
