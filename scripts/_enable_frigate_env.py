#!/usr/bin/env python3
"""Append Frigate flags to .env if missing (idempotent)."""
from __future__ import annotations

import sys
from pathlib import Path

BLOCK = """
# --- Frigate (media plane — enabled for live cam 108) ---
FRIGATE_ENABLED=1
FRIGATE_CONFIG_SYNC=1
FRIGATE_LIVE=1
FRIGATE_EVIDENCE=1
FRIGATE_EVENTS=0
FRIGATE_URL=http://127.0.0.1:5000
EVIDENCE_BACKEND=frigate
FRIGATE_BASE_YAML={root}/infra/frigate.base.yaml
FRIGATE_CONFIG_PATH={root}/infra/frigate-config/config.yml
FRIGATE_GENERATED_DIR={root}/infra/frigate-config
FRIGATE_INPUT_VIA_GO2RTC=0
FRIGATE_GO2RTC_HOST=citevision-v2-go2rtc
FRIGATE_GO2RTC_PORT=8554
VITE_FRIGATE_ENABLED=1
VITE_FRIGATE_LIVE=1
"""


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "citevision-v2"
    env = root / ".env"
    if not env.is_file():
        print(f"MISSING {env}", file=sys.stderr)
        return 1
    text = env.read_text(encoding="utf-8")
    root_s = str(root.resolve())
    if "FRIGATE_ENABLED" in text:
        lines = []
        have = {"base": False, "config": False, "dir": False, "via": False, "host": False, "port": False, "evidence": False, "backend": False}
        for line in text.splitlines():
            if line.startswith("FRIGATE_BASE_YAML="):
                lines.append(f"FRIGATE_BASE_YAML={root_s}/infra/frigate.base.yaml")
                have["base"] = True
            elif line.startswith("FRIGATE_CONFIG_PATH="):
                lines.append(f"FRIGATE_CONFIG_PATH={root_s}/infra/frigate-config/config.yml")
                have["config"] = True
            elif line.startswith("FRIGATE_GENERATED_DIR="):
                lines.append(f"FRIGATE_GENERATED_DIR={root_s}/infra/frigate-config")
                have["dir"] = True
            elif line.startswith("FRIGATE_INPUT_VIA_GO2RTC="):
                lines.append("FRIGATE_INPUT_VIA_GO2RTC=0")
                have["via"] = True
            elif line.startswith("FRIGATE_GO2RTC_HOST="):
                lines.append("FRIGATE_GO2RTC_HOST=citevision-v2-go2rtc")
                have["host"] = True
            elif line.startswith("FRIGATE_GO2RTC_PORT="):
                lines.append("FRIGATE_GO2RTC_PORT=8554")
                have["port"] = True
            elif line.startswith("FRIGATE_EVIDENCE="):
                lines.append("FRIGATE_EVIDENCE=1")
                have["evidence"] = True
            elif line.startswith("EVIDENCE_BACKEND="):
                lines.append("EVIDENCE_BACKEND=frigate")
                have["backend"] = True
            else:
                lines.append(line)
        if not have["base"]:
            lines.append(f"FRIGATE_BASE_YAML={root_s}/infra/frigate.base.yaml")
        if not have["config"]:
            lines.append(f"FRIGATE_CONFIG_PATH={root_s}/infra/frigate-config/config.yml")
        if not have["dir"]:
            lines.append(f"FRIGATE_GENERATED_DIR={root_s}/infra/frigate-config")
        if not have["via"]:
            lines.append("FRIGATE_INPUT_VIA_GO2RTC=0")
        if not have["host"]:
            lines.append("FRIGATE_GO2RTC_HOST=citevision-v2-go2rtc")
        if not have["port"]:
            lines.append("FRIGATE_GO2RTC_PORT=8554")
        if not have["evidence"]:
            lines.append("FRIGATE_EVIDENCE=1")
        if not have["backend"]:
            lines.append("EVIDENCE_BACKEND=frigate")
        env.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        print("UPDATED_FRIGATE_PATHS")
        return 0
    env.write_text(text.rstrip() + "\n" + BLOCK.format(root=root_s), encoding="utf-8")
    print("APPENDED_FRIGATE_FLAGS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
