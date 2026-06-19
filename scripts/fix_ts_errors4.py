#!/usr/bin/env python3
"""Fix the last TS error in RuleActivationDialog - caption type."""
from pathlib import Path

dialog_file = Path("frontend/src/components/rules/RuleActivationDialog.tsx")
content = dialog_file.read_text(encoding="utf-8")

# caption={activeTemplate.tutorial} — tutorial is string|undefined but inside && guard
# Cast to string to satisfy ReactNode typing
OLD_CAPTION = "          caption={activeTemplate.tutorial}"
NEW_CAPTION = "          caption={activeTemplate.tutorial as string}"
if OLD_CAPTION in content:
    content = content.replace(OLD_CAPTION, NEW_CAPTION)
    print("Fixed caption cast")
else:
    print("Caption anchor not found - searching...")
    import re
    for i, line in enumerate(content.split('\n'), 1):
        if 'caption' in line and 'tutorial' in line:
            print(f"L{i}: {line}")

dialog_file.write_text(content, encoding="utf-8")
