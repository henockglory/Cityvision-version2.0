#!/usr/bin/env python3
"""Fix remaining TS errors in RuleCatalogPanel."""
from pathlib import Path

panel_file = Path("frontend/src/components/rules/RuleCatalogPanel.tsx")
content = panel_file.read_text(encoding="utf-8")

# Fix pre-existing t() call with bare string second arg
OLD = "t(`rules.severity.${tpl.severity}`, tpl.severity ?? '')"
NEW = "t(`rules.severity.${tpl.severity}`, { defaultValue: tpl.severity ?? '' })"
if OLD in content:
    content = content.replace(OLD, NEW)
    print("Fixed t(severity) call")

# Check RuleCard t prop — make sure PartialStatusBadge receives compatible t
# The RuleCard t prop is typed correctly; PartialStatusBadge's t should accept
# (k: string, opts?: Record<string,unknown>) since that's what's passed
# This should now be consistent

panel_file.write_text(content, encoding="utf-8")
print("Done")
