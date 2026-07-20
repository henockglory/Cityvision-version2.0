#!/usr/bin/env python3
"""Train/export seatbelt ONNX only (Roboflow fay-regu8/seat_belt or HF fallback)."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "ai-engine" / "models" / "secondary" / "seatbelt.onnx"


def main() -> int:
    from ultralytics import YOLO

    work = DEST.parent / "_build_seatbelt"
    work.mkdir(parents=True, exist_ok=True)
    api_key = os.environ.get("ROBOFLOW_API_KEY", "")

    if api_key:
        try:
            from roboflow import Roboflow

            rf = Roboflow(api_key=api_key)
            ds = rf.universe("fay-regu8/seat_belt-iauiy").version(1).download("yolov8", location=str(work / "ds"))
            data_yaml = Path(ds.location) / "data.yaml"
            print(f"Training on {data_yaml}")
            model = YOLO("yolov8n.pt")
            model.train(
                data=str(data_yaml),
                epochs=int(os.environ.get("SEATBELT_EPOCHS", "25")),
                imgsz=640,
                batch=8,
                device=0 if os.environ.get("CUDA_VISIBLE_DEVICES", "") != "-1" else "cpu",
                project=str(work),
                name="train",
                exist_ok=True,
            )
            best = work / "train" / "weights" / "best.pt"
            if best.exists():
                out = Path(YOLO(str(best)).export(format="onnx", imgsz=640, simplify=True))
                shutil.copy2(out, DEST)
                print(f"[OK] {DEST}")
                return 0
        except Exception as exc:
            print(f"[WARN] roboflow train: {exc}")

    # HF fallback: mobile + seatbelt combined detector (public universe export via ultralytics)
    try:
        from huggingface_hub import hf_hub_download

        for repo, fname in (
            ("Safe-Drive-TN/State-farm-detection", "best.pt"),  # wrong task
        ):
            pass
        # Try keremberke seatbelt if exists
        for repo in (
            "keremberke/yolov8n-seatbelt-detection",
            "keremberke/yolov8m-seatbelt-detection",
        ):
            try:
                pt = hf_hub_download(repo_id=repo, filename="best.pt")
                model = YOLO(pt)
                out = Path(model.export(format="onnx", imgsz=640, simplify=True))
                shutil.copy2(out, DEST)
                print(f"[OK] seatbelt from HF {repo}")
                return 0
            except Exception:
                continue
    except Exception as exc:
        print(f"[WARN] HF seatbelt: {exc}")

    # Last resort: quick train on mobile-and-seatbelt via roboflow universe wget (needs key)
    print("[ERR] Set ROBOFLOW_API_KEY in .env for seatbelt training, or place seatbelt.onnx manually")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
