from pathlib import Path

s = Path("/mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py")
d = Path("/home/gheno/citevision-v2/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py")
t = s.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
assert "import urllib.error" in t
assert "ship partial" in t
d.write_text(t, encoding="utf-8", newline="\n")
print("synced_full_ok")
