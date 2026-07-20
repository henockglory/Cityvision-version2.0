from pathlib import Path
src_root = Path("/mnt/c/Users/gheno/citevision")
dst_root = Path.home() / "citevision-v2"
files = [
    "backend/internal/camera/service.go",
    "backend/internal/camera/wizard.go",
    "backend/internal/handler/api.go",
    "backend/internal/ingest/orchestrator.go",
    "frontend/src/pages/Cameras.tsx",
    "frontend/src/api/client.ts",
    "frontend/src/i18n/fr.json",
    "frontend/src/i18n/en.json",
]
for rel in files:
    src = src_root / rel
    dst = dst_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = src.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    dst.write_text(text, encoding="utf-8", newline="\n")
    print("OK:", rel)
