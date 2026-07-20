#!/usr/bin/env python3
from pathlib import Path

f = Path("frontend/src/components/rules/RuleActivationDialog.tsx")
content = f.read_text(encoding="utf-8")

OLD = '      <WizardSteps steps={wizardSteps} current={step} className="mb-4" />'
NEW = '''      <WizardSteps steps={wizardSteps} current={step} className="mb-4" />
      <WizardStepContext step={step} template={activeTemplate as { name: string; partial_status?: string; partial_reason_fr?: string; category?: string }} t={t} />'''

if OLD in content and 'WizardStepContext step={step}' not in content:
    content = content.replace(OLD, NEW)
    f.write_text(content, encoding="utf-8")
    print("Added WizardStepContext usage ✓")
else:
    print("Already present or anchor not found")
