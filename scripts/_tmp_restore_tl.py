from pathlib import Path

head = Path("/tmp/tl_head.py").read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
for p in [
    Path("/home/gheno/citevision-v2/ai-engine/src/citevision_ai/road_enforcement/traffic_light.py"),
    Path("/mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/road_enforcement/traffic_light.py"),
]:
    p.write_text(head, encoding="utf-8", newline="\n")
    print("wrote", p, "prefer_red", "Prefer red" in head)
