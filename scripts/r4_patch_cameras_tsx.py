#!/usr/bin/env python3
"""
R4 – Patch frontend/src/pages/Cameras.tsx to:
  1. Store ffprobe result from probe.data.ffprobe
  2. Display codec/resolution/fps in the wizard step 2 success block
  3. Add ffprobe warning for partial results
"""
from pathlib import Path

cameras_file = Path("frontend/src/pages/Cameras.tsx")
content = cameras_file.read_text(encoding="utf-8")

if 'ffprobe' in content:
    print("Cameras.tsx already patched")
    exit(0)

# 1. Add ffprobeInfo state after testOk state
OLD_STATE = "  const [testOk, setTestOk] = useState(false);\n  const [detectedVendor, setDetectedVendor] = useState('generic');"
NEW_STATE = "  const [testOk, setTestOk] = useState(false);\n  const [detectedVendor, setDetectedVendor] = useState('generic');\n  const [ffprobeInfo, setFfprobeInfo] = useState<{ video_codec?: string; width?: number; height?: number; fps?: number; error?: string; available?: boolean } | null>(null);"
content = content.replace(OLD_STATE, NEW_STATE)

# 2. Store ffprobe result from probe response
OLD_BEST = "        const best = probe.data.best;\n        vendor = best?.vendor ?? vendor;\n        detectedRtspPath = best?.rtsp_path ?? detectedRtspPath;\n      }"
NEW_BEST = "        const best = probe.data.best;\n        vendor = best?.vendor ?? vendor;\n        detectedRtspPath = best?.rtsp_path ?? detectedRtspPath;\n        if (probe.data.ffprobe) setFfprobeInfo(probe.data.ffprobe);\n      }"
content = content.replace(OLD_BEST, NEW_BEST)

# 3. Reset ffprobe state on reset
OLD_RESET = "    setTestOk(false);\n    setDetectedVendor('generic');"
NEW_RESET = "    setTestOk(false);\n    setDetectedVendor('generic');\n    setFfprobeInfo(null);"
content = content.replace(OLD_RESET, NEW_RESET, 1)  # Only replace first occurrence (main reset)

# 4. Show ffprobe info in step 2 success block (where detectedVendor is shown)
OLD_VENDOR_DISPLAY = """                  <p className="text-xs text-center text-cv-muted">
                    {t('cameras.wizard.detectedVendor', 'Profil détecté')}: <span className="font-mono text-cv-accent">{detectedVendor}</span>
                  </p>"""
NEW_VENDOR_DISPLAY = """                  <p className="text-xs text-center text-cv-muted">
                    {t('cameras.wizard.detectedVendor', 'Profil détecté')}: <span className="font-mono text-cv-accent">{detectedVendor}</span>
                  </p>
                  {ffprobeInfo?.video_codec && (
                    <p className="text-xs text-center text-emerald-400/80">
                      {ffprobeInfo.video_codec.toUpperCase()}
                      {ffprobeInfo.width ? ` · ${ffprobeInfo.width}×${ffprobeInfo.height}` : ''}
                      {ffprobeInfo.fps ? ` · ${ffprobeInfo.fps} fps` : ''}
                    </p>
                  )}
                  {ffprobeInfo?.available && ffprobeInfo.error && (
                    <p className="text-xs text-center text-amber-400">
                      {t('cameras.wizard.ffprobeWarn')}: {ffprobeInfo.error}
                    </p>
                  )}
                  {ffprobeInfo && !ffprobeInfo.available && (
                    <p className="text-xs text-center text-cv-muted/60">
                      {t('cameras.wizard.ffprobeNotInstalled', 'Validation approfondie indisponible (ffprobe absent)')}
                    </p>
                  )}"""
content = content.replace(OLD_VENDOR_DISPLAY, NEW_VENDOR_DISPLAY)

cameras_file.write_text(content, encoding="utf-8")
print("Patched Cameras.tsx with ffprobe display")
