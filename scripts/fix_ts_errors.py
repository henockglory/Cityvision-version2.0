#!/usr/bin/env python3
"""Fix TypeScript errors introduced by R1-R4 patches."""
from pathlib import Path
import re

# ──────────────────────────────────────────────────────────────────────────────
# 1. Fix RuleActivationFeedback.tsx
#    - Remove unused ruleName param usage
#    - Fix eventsApi.list() call (cameraId → camera_id, .data access)
# ──────────────────────────────────────────────────────────────────────────────
feedback_file = Path("frontend/src/components/rules/RuleActivationFeedback.tsx")
content = feedback_file.read_text(encoding="utf-8")

# Fix import - eventsApi returns AxiosResponse, need to access .data
OLD_IMPORT = "import { eventsApi } from '@/api/client';"
NEW_IMPORT = "import { eventsApi } from '@/api/client';\nimport type { Event } from '@/types';"
content = content.replace(OLD_IMPORT, NEW_IMPORT)

# Fix ruleName unused - just remove the prop from destructuring (keep in interface)
OLD_DESTRUCTURE = """  ruleName,
  cameraId,"""
NEW_DESTRUCTURE = """  cameraId,"""
content = content.replace(OLD_DESTRUCTURE, NEW_DESTRUCTURE)

# Fix eventsApi.list() call - use camera_id instead of cameraId, and access .data
OLD_EVENTS_CALL = """        const events = await eventsApi.list(orgId, { cameraId, limit: 5 });
        const recent = events.filter((e: { timestamp: string }) => new Date(e.timestamp).getTime() >= activatedAt - 5000);"""
NEW_EVENTS_CALL = """        const resp = await eventsApi.list(orgId, { camera_id: cameraId, limit: 5 });
        const events: Event[] = Array.isArray(resp.data) ? resp.data : (resp as unknown as Event[]);
        const recent = events.filter((e: Event) => new Date(e.timestamp).getTime() >= activatedAt - 5000);"""
content = content.replace(OLD_EVENTS_CALL, NEW_EVENTS_CALL)

feedback_file.write_text(content, encoding="utf-8")
print("Fixed RuleActivationFeedback.tsx")

# ──────────────────────────────────────────────────────────────────────────────
# 2. Fix RuleActivationDialog.tsx
#    - isOpen → open prop (check what Modal accepts)
#    - Fix type error on TS2322 (unknown -> ReactNode)
# ──────────────────────────────────────────────────────────────────────────────
dialog_file = Path("frontend/src/components/rules/RuleActivationDialog.tsx")
content = dialog_file.read_text(encoding="utf-8")

# Fix: Modal uses 'open' not 'isOpen' in feedback overlay
# Also: title might need different form
OLD_FEEDBACK_MODAL = """      <Modal
        isOpen
        onClose={() => { setShowFeedback(false); onClose(); }}
        title={activeTemplate.name}
        size="sm"
      >"""
NEW_FEEDBACK_MODAL = """      <Modal
        open
        onClose={() => { setShowFeedback(false); onClose(); }}
        title={activeTemplate.name}
        size="sm"
      >"""
content = content.replace(OLD_FEEDBACK_MODAL, NEW_FEEDBACK_MODAL)

dialog_file.write_text(content, encoding="utf-8")
print("Fixed RuleActivationDialog.tsx (isOpen→open)")

# ──────────────────────────────────────────────────────────────────────────────
# 3. Fix RuleCatalogPanel.tsx
#    - PartialStatusBadge t() called with string arg not Record
# ──────────────────────────────────────────────────────────────────────────────
panel_file = Path("frontend/src/components/rules/RuleCatalogPanel.tsx")
content = panel_file.read_text(encoding="utf-8")

# The t() function signature issue — change to use defaultValue
OLD_T_CALL = "    label: t('rules.partial.requires_calibration'),"
if OLD_T_CALL in content:
    # Replace all t('rules.partial.xxx') calls to use { defaultValue } style
    # Actually the issue is the t function type signature in PartialStatusBadge
    # Change the t parameter type
    OLD_T_TYPE = "t: (k: string, opts?: Record<string, unknown>) => string }) {"
    NEW_T_TYPE = "t: (k: string, opts?: unknown) => string }) {"
    content = content.replace(OLD_T_TYPE, NEW_T_TYPE)
    panel_file.write_text(content, encoding="utf-8")
    print("Fixed RuleCatalogPanel.tsx (t type)")
else:
    print("RuleCatalogPanel.tsx t-type fix not needed")

# ──────────────────────────────────────────────────────────────────────────────
# 4. Fix Cameras.tsx
#    - setDetectedVendor vendor type mismatch
#    - probe.data.ffprobe TypeScript type
# ──────────────────────────────────────────────────────────────────────────────
cameras_file = Path("frontend/src/pages/Cameras.tsx")
content = cameras_file.read_text(encoding="utf-8")

# Fix vendor type: cast as the correct union type
OLD_VENDOR = "        vendor = best?.vendor ?? vendor;"
NEW_VENDOR = "        vendor = (best?.vendor as 'hikvision' | 'dahua' | 'generic') ?? vendor;"
content = content.replace(OLD_VENDOR, NEW_VENDOR)

# Fix ffprobe access on probe.data (needs type assertion)
OLD_FFPROBE = "        if (probe.data.ffprobe) setFfprobeInfo(probe.data.ffprobe);"
# eslint-disable-next-line @typescript-eslint/no-explicit-any
NEW_FFPROBE = "        if ((probe.data as Record<string, unknown>).ffprobe) setFfprobeInfo((probe.data as Record<string, unknown>).ffprobe as typeof ffprobeInfo);"
content = content.replace(OLD_FFPROBE, NEW_FFPROBE)

cameras_file.write_text(content, encoding="utf-8")
print("Fixed Cameras.tsx (vendor type + ffprobe access)")

print("\nAll TypeScript fixes applied")
