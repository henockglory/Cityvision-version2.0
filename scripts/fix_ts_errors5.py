#!/usr/bin/env python3
"""Fix the definition?.pipeline unknown ReactNode issue."""
from pathlib import Path

dialog_file = Path("frontend/src/components/rules/RuleActivationDialog.tsx")
content = dialog_file.read_text(encoding="utf-8")

# The issue: activeTemplate.definition?.pipeline is `unknown` type
# because definition is Record<string, unknown>
# When used as a JSX guard condition, TS complains it can't be ReactNode
# Fix: use !! to convert to boolean
OLD = "{step === 1 && activeTemplate.definition?.pipeline && ("
NEW = "{step === 1 && !!activeTemplate.definition?.pipeline && ("
if OLD in content:
    content = content.replace(OLD, NEW)
    print("Fixed pipeline unknown condition")
    dialog_file.write_text(content, encoding="utf-8")
else:
    print("Anchor not found - searching for similar patterns...")
    import re
    for i, line in enumerate(content.split('\n'), 1):
        if 'pipeline' in line and 'definition' in line:
            print(f"L{i}: {line}")
