"""Load shared AI model registries (primary + secondary ONNX)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
REGISTRY = ROOT / "shared" / "ai-stack-registry.json"
SECONDARY = ROOT / "shared" / "ai-models.json"


def load_stack_registry() -> dict[str, Any]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def load_secondary_registry() -> dict[str, Any]:
    if not SECONDARY.exists():
        return {"models": []}
    return json.loads(SECONDARY.read_text(encoding="utf-8"))


def required_health_keys() -> list[str]:
    """All health keys that must be true before AI engine is considered ready."""
    reg = load_stack_registry()
    keys: list[str] = []
    for spec in reg.get("models", []):
        if spec.get("required", True):
            keys.append(str(spec["health_key"]))
    suffix = str(reg.get("secondary_health_suffix", "_model_loaded"))
    for spec in load_secondary_registry().get("models", []):
        if spec.get("required", True):
            keys.append(f"{spec['id']}{suffix}")
    gpu_key = reg.get("gpu_health_key")
    if gpu_key:
        keys.append(str(gpu_key))
    return keys


def model_catalog() -> list[dict[str, Any]]:
    """Flat catalog for /health and install docs."""
    reg = load_stack_registry()
    suffix = str(reg.get("secondary_health_suffix", "_model_loaded"))
    out: list[dict[str, Any]] = []
    for spec in reg.get("models", []):
        out.append(
            {
                "id": spec["id"],
                "health_key": spec["health_key"],
                "kind": spec.get("kind", "primary"),
                "required": spec.get("required", True),
            }
        )
    for spec in load_secondary_registry().get("models", []):
        out.append(
            {
                "id": spec["id"],
                "health_key": f"{spec['id']}{suffix}",
                "kind": "secondary",
                "required": True,
                "file": spec.get("file"),
                "behavior": spec.get("behavior"),
            }
        )
    return out
