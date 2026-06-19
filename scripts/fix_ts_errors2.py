#!/usr/bin/env python3
"""Fix remaining TypeScript errors."""
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# 1. Fix RuleActivationDialog.tsx feedback modal (remove `size` → use `maxWidth`)
# ──────────────────────────────────────────────────────────────────────────────
dialog_file = Path("frontend/src/components/rules/RuleActivationDialog.tsx")
content = dialog_file.read_text(encoding="utf-8")

OLD_MODAL_SIZE = '''      <Modal
        open
        onClose={() => { setShowFeedback(false); onClose(); }}
        title={activeTemplate.name}
        size="sm"
      >'''
NEW_MODAL_SIZE = '''      <Modal
        open
        onClose={() => { setShowFeedback(false); onClose(); }}
        title={activeTemplate.name}
        maxWidth="sm"
      >'''
content = content.replace(OLD_MODAL_SIZE, NEW_MODAL_SIZE)

# Fix line 504: Type 'unknown' not assignable to ReactNode
# This is probably a children type issue — let me look at context
# Line 504 is "className="mb-4"" based on grep result - inside a GuideIllustration or similar
# Let me find and look at it

# Actually this may be a pre-existing error unrelated to our changes
# Let's check if it was there before by searching for the pattern
if 'unknown' in content:
    # Look for the specific issue - likely in pipeline steps rendering
    OLD_PIPELINE_STEPS = '''            {(Array.isArray((activeTemplate.tutorial as { steps?: string[] })?.steps)
              ? (activeTemplate.tutorial as { steps: string[] }).steps
              : ['''
    NEW_PIPELINE_STEPS = '''            {(Array.isArray((activeTemplate.tutorial as unknown as { steps?: string[] })?.steps)
              ? (activeTemplate.tutorial as unknown as { steps: string[] }).steps
              : ['''
    if OLD_PIPELINE_STEPS in content:
        content = content.replace(OLD_PIPELINE_STEPS, NEW_PIPELINE_STEPS)
        print("Fixed pipeline steps type cast")

dialog_file.write_text(content, encoding="utf-8")
print("Fixed RuleActivationDialog.tsx")

# ──────────────────────────────────────────────────────────────────────────────
# 2. Fix RuleActivationFeedback.tsx - remove limit from eventsApi.list params
# ──────────────────────────────────────────────────────────────────────────────
feedback_file = Path("frontend/src/components/rules/RuleActivationFeedback.tsx")
content = feedback_file.read_text(encoding="utf-8")

OLD_EVENTS = "        const resp = await eventsApi.list(orgId, { camera_id: cameraId, limit: 5 });"
NEW_EVENTS = "        const resp = await eventsApi.list(orgId, { camera_id: cameraId });"
content = content.replace(OLD_EVENTS, NEW_EVENTS)

feedback_file.write_text(content, encoding="utf-8")
print("Fixed RuleActivationFeedback.tsx (removed limit param)")

# ──────────────────────────────────────────────────────────────────────────────
# 3. Fix RuleCatalogPanel.tsx - use correct t() signature
#    The issue is that the t function passed to PartialStatusBadge has a specific
#    type (k: string, opts?: Record<string,unknown>) but we declared opts?: unknown
#    Fix: just inline the t call without options (the keys have defaultValues)
# ──────────────────────────────────────────────────────────────────────────────
panel_file = Path("frontend/src/components/rules/RuleCatalogPanel.tsx")
content = panel_file.read_text(encoding="utf-8")

# Revert the t type and instead just don't use opts in PartialStatusBadge
OLD_T_SIG = "t: (k: string, opts?: unknown) => string }) {"
NEW_T_SIG = "t: (k: string, opts?: Record<string, unknown>) => string }) {"
content = content.replace(OLD_T_SIG, NEW_T_SIG)

# The error at line 150 is t('rules.partial.requires_calibration') — no opts
# but the type says opts?: Record<...>. This is fine since opts is optional.
# The real error might be somewhere else - let me check
# Error: "Argument of type 'string' is not assignable to parameter of type 'Record<string, unknown>'"
# This suggests t is called as t(key, string) somewhere

# Find the offending call
import re
matches = list(re.finditer(r"t\('rules\.partial\.[^']+',\s*[^)]+\)", content))
for m in matches:
    print(f"t call: {m.group()[:80]}")

# The label values are just strings like t('rules.partial.requires_calibration')
# without extra args - should be fine. Let me check around line 150
lines = content.split('\n')
for i, line in enumerate(lines, 1):
    if 'rules.partial.' in line:
        print(f"L{i}: {line}")

panel_file.write_text(content, encoding="utf-8")
