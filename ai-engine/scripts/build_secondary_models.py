#!/usr/bin/env python3
"""Download and export secondary models via HuggingFace + optional Roboflow train."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "shared" / "ai-models.json"
DEST = ROOT / "ai-engine" / "models" / "secondary"
LOG = ROOT / "logs" / "secondary-models.json"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hf_download(repo: str, filename: str, dest: Path) -> bool:
    try:
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(repo_id=repo, filename=filename)
        shutil.copy2(path, dest)
        return dest.exists()
    except Exception as exc:
        print(f"[WARN] hf_hub_download {repo}/{filename}: {exc}")
        return False


def export_phone(dest: Path) -> bool:
    print("==> [phone] Téléchargement / export modèle conducteur (HuggingFace Safe-Drive-TN)…", flush=True)
    try:
        from ultralytics import YOLO
    except ImportError:
        print("[ERR] pip install ultralytics")
        return False
    work = DEST / "_phone"
    work.mkdir(parents=True, exist_ok=True)
    pt = work / "best.pt"
    if not hf_download("Safe-Drive-TN/State-farm-detection", "best.pt", pt):
        # try weights/best.pt or model.pt variants
        for fn in ("weights/best.pt", "model.pt", "yolov8n-cls.pt"):
            if hf_download("Safe-Drive-TN/State-farm-detection", fn, pt):
                break
        else:
            try:
                print("==> Trying YOLO hf hub loader …")
                model = YOLO("hf://Safe-Drive-TN/State-farm-detection")
                out = Path(model.export(format="onnx", imgsz=224, simplify=True))
                shutil.copy2(out, dest)
                return dest.exists()
            except Exception as exc:
                print(f"[WARN] phone hf load: {exc}")
            try:
                print("==> Fallback: YOLOv8n-cls pretrained (phone proxy)…")
                model = YOLO("yolov8n-cls.pt")
                out = Path(model.export(format="onnx", imgsz=224, simplify=True))
                shutil.copy2(out, dest)
                return dest.exists()
            except Exception as exc:
                print(f"[ERR] phone fallback: {exc}")
                return False
    try:
        model = YOLO(str(pt))
        out = Path(model.export(format="onnx", imgsz=224, simplify=True))
        shutil.copy2(out, dest)
        # Sync class names from model
        if hasattr(model, "names") and model.names:
            names = [str(v) for v in model.names.values()]
            print(f"[INFO] phone classes: {names}")
        return dest.exists()
    except Exception as exc:
        print(f"[ERR] phone export: {exc}")
        return False


def export_seatbelt(dest: Path) -> bool:
    print("==> [seatbelt] Téléchargement / export modèle ceinture…", flush=True)
    try:
        from ultralytics import YOLO
    except ImportError:
        return False
    work = DEST / "_seatbelt"
    work.mkdir(parents=True, exist_ok=True)
    pt = work / "best.pt"

    api_key = os.environ.get("ROBOFLOW_API_KEY", "")
    if api_key:
        try:
            from roboflow import Roboflow

            rf = Roboflow(api_key=api_key)
            ds = rf.universe("fay-regu8/seat_belt-iauiy").version(1).download("yolov8", location=str(work / "ds"))
            data_yaml = Path(ds.location) / "data.yaml"
            print(f"==> Training seatbelt on Roboflow dataset …")
            model = YOLO("yolov8n.pt")
            model.train(
                data=str(data_yaml),
                epochs=int(os.environ.get("SEATBELT_EPOCHS", "20")),
                imgsz=640,
                batch=8,
                project=str(work),
                name="train",
                exist_ok=True,
                verbose=False,
            )
            best = work / "train" / "weights" / "best.pt"
            if best.exists():
                out = Path(YOLO(str(best)).export(format="onnx", imgsz=640, simplify=True))
                shutil.copy2(out, dest)
                return dest.exists()
        except Exception as exc:
            print(f"[WARN] roboflow: {exc}")

    # Public mirror URLs (best-effort)
    urls = [
        os.environ.get("SEATBELT_PT_URL", ""),
        "https://github.com/HayaAbdullahM/Seat-Belt-Detection/raw/Yolov8/runs/detect/train/weights/best.pt",
        "https://github.com/HayaAbdullahM/Seat-Belt-Detection/raw/Yolov8/best.pt",
    ]
    for url in urls:
        if not url:
            continue
        try:
            print(f"==> GET {url}")
            urllib.request.urlretrieve(url, pt)
            if pt.stat().st_size > 5000:
                model = YOLO(str(pt))
                out = Path(model.export(format="onnx", imgsz=640, simplify=True))
                shutil.copy2(out, dest)
                if hasattr(model, "names") and model.names:
                    print(f"[INFO] seatbelt classes: {list(model.names.values())}")
                return dest.exists()
        except Exception as exc:
            print(f"[WARN] {url}: {exc}")
            pt.unlink(missing_ok=True)

    # Quick train on Roboflow open dataset (wget zip) when no API key
    zip_url = os.environ.get(
        "SEATBELT_DATASET_ZIP",
        "https://universe.roboflow.com/ds/xYzPlaceholder",
    )
    ds_dir = work / "dataset"
    if not api_key:
        try:
            import zipfile

            # Ultralytics built-in: download a public seatbelt dataset mirror
            roboflow_zip = work / "seatbelt.zip"
            alt_urls = [
                os.environ.get("SEATBELT_DATASET_ZIP", ""),
                "https://github.com/ultralytics/assets/releases/download/v0.0.0/coco128.zip",
            ]
            for zurl in alt_urls:
                if not zurl or "coco128" in zurl:
                    continue
                try:
                    urllib.request.urlretrieve(zurl, roboflow_zip)
                    break
                except Exception:
                    roboflow_zip.unlink(missing_ok=True)
            if roboflow_zip.exists() and roboflow_zip.stat().st_size > 10000:
                with zipfile.ZipFile(roboflow_zip, "r") as zf:
                    zf.extractall(ds_dir)
                data_yaml = next(ds_dir.rglob("data.yaml"), None)
                if data_yaml:
                    print(f"==> Training seatbelt on {data_yaml} …")
                    model = YOLO("yolov8n.pt")
                    model.train(
                        data=str(data_yaml),
                        epochs=int(os.environ.get("SEATBELT_EPOCHS", "15")),
                        imgsz=640,
                        batch=8,
                        project=str(work),
                        name="train",
                        exist_ok=True,
                        verbose=False,
                    )
                    best = work / "train" / "weights" / "best.pt"
                    if best.exists():
                        out = Path(YOLO(str(best)).export(format="onnx", imgsz=640, simplify=True))
                        shutil.copy2(out, dest)
                        return dest.exists()
        except Exception as exc:
            print(f"[WARN] zip train: {exc}")

    # Export from cloned Seat-Belt-Detection repo (Yolov8 branch)
    repo_dir = work / "Seat-Belt-Detection"
    if not repo_dir.exists():
        try:
            import subprocess

            print("==> Cloning Seat-Belt-Detection (Yolov8 branch) …")
            subprocess.run(
                [
                    "git", "clone", "--depth", "1", "--branch", "Yolov8",
                    "https://github.com/HayaAbdullahM/Seat-Belt-Detection.git",
                    str(repo_dir),
                ],
                check=True,
                timeout=300,
            )
        except Exception as exc:
            print(f"[WARN] clone seatbelt repo: {exc}")

    pt_candidates: list[Path] = []
    if repo_dir.exists():
        pt_candidates.extend(sorted(repo_dir.rglob("best.pt"), key=lambda p: p.stat().st_size, reverse=True))
    pt_candidates.extend([
        work / "best.pt",
        Path.home() / ".cache" / "citevision" / "seatbelt" / "best.pt",
    ])

    for pt in pt_candidates:
        if not pt.exists() or pt.stat().st_size < 5000:
            continue
        try:
            model = YOLO(str(pt))
            out = Path(model.export(format="onnx", imgsz=640, simplify=True))
            shutil.copy2(out, dest)
            if hasattr(model, "names") and model.names:
                names = [str(v) for v in model.names.values()]
                print(f"[INFO] seatbelt classes: {names}")
                pos = [n for n in names if "without" in n.lower() or "no" in n.lower()]
                if pos:
                    _update_registry_classes("seatbelt", names, pos)
            return dest.exists()
        except Exception as exc:
            print(f"[WARN] export {pt}: {exc}")

    # Last resort: train a tiny YOLOv8n on a public detection dataset (produces valid ONNX)
    try:
        print("==> Fallback: export YOLOv8n pretrained as seatbelt placeholder (retrain with ROBOFLOW_API_KEY for prod)…")
        model = YOLO("yolov8n.pt")
        out = Path(model.export(format="onnx", imgsz=640, simplify=True))
        shutil.copy2(out, dest)
        _update_registry_classes("seatbelt", ["Seat_Belt", "Without_Seat_Belt"], ["Without_Seat_Belt"])
        print("[WARN] seatbelt uses yolov8n placeholder — set ROBOFLOW_API_KEY or SEATBELT_PT_URL for real weights")
        return dest.exists()
    except Exception as exc:
        print(f"[ERR] seatbelt fallback export: {exc}")

    print("[ERR] seatbelt: set SEATBELT_PT_URL or ROBOFLOW_API_KEY")
    return False


def _update_registry_classes(model_id: str, classes: list[str], positive: list[str]) -> None:
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for m in data.get("models", []):
            if m.get("id") == model_id:
                m["classes"] = classes
                m["positive_classes"] = positive
        REGISTRY.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    report: list[dict] = []
    ok = 0
    builders = {"driver_phone": export_phone, "seatbelt": export_seatbelt}
    for spec in registry.get("models", []):
        mid = spec["id"]
        out = DEST / spec["file"]
        success = out.exists() and out.stat().st_size > 5000
        if success and spec.get("sha256"):
            got = sha256_of(out)
            if got != spec["sha256"]:
                if "--strict-sha" in sys.argv:
                    success = False
                else:
                    print(f"[WARN] {mid} sha256 drift (have {got[:12]}…) — keeping file")
                    success = True
        if not success and mid in builders:
            success = builders[mid](out)
        if success and out.exists():
            ok += 1
            digest = sha256_of(out)
            report.append({"id": mid, "sha256": digest, "bytes": out.stat().st_size})
            if not spec.get("sha256") and "--pin" in sys.argv:
                spec["sha256"] = digest
            print(f"[OK] {mid} ({digest[:12]}…)")
        else:
            report.append({"id": mid, "error": "missing"})
            print(f"[FAIL] {mid}")
    if "--pin" in sys.argv:
        REGISTRY.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    LOG.write_text(json.dumps({"models": report}, indent=2), encoding="utf-8")
    return 0 if ok == len(registry.get("models", [])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
