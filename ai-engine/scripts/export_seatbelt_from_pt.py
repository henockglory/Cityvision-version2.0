#!/usr/bin/env python3
from pathlib import Path
from ultralytics import YOLO
import shutil
import json

pt = Path("/tmp/sbd/yolov8/content/runs/detect/train2/weights/best.pt")
if not pt.exists():
    raise SystemExit(f"missing {pt}")

root = Path(__file__).resolve().parents[2]
dest = root / "ai-engine/models/secondary/seatbelt.onnx"
registry = root / "shared/ai-models.json"

model = YOLO(str(pt))
names = [str(v) for v in model.names.values()]
print("classes:", names)

out = Path(model.export(format="onnx", imgsz=640, simplify=True))
shutil.copy2(out, dest)
print("OK", dest, dest.stat().st_size)

# Update registry classes to match trained model
data = json.loads(registry.read_text(encoding="utf-8"))
for m in data.get("models", []):
    if m.get("id") == "seatbelt":
        m["classes"] = names
        pos = [n for n in names if "no" in n.lower() or n in ("0", "no_seatbelt", "No Seatbelt", "no seatbelt")]
        if not pos and len(names) == 1:
            pos = names
        elif not pos and len(names) >= 2:
            pos = [names[-1]]
        m["positive_classes"] = pos
        print("positive_classes:", pos)
registry.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
