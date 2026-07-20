#!/usr/bin/env python3
"""
Patch RuleCatalogPanel.tsx to show partial_status badges on rule cards.
Badge types:
  - requires_calibration → orange "Calibration requise"
  - requires_ocr         → purple "Module OCR requis"
  - requires_face_ai     → purple "Module Visage requis"
  - partial_aggregate    → yellow "Données partielles"
"""
from pathlib import Path

panel_file = Path("frontend/src/components/rules/RuleCatalogPanel.tsx")
content = panel_file.read_text(encoding="utf-8")

if 'partial_status' in content:
    print("Already patched")
    exit(0)

# 1) Add FlaskConical to Lucide imports
OLD_IMPORTS = "import { Check, ChevronDown, Clock, PowerOff, Search } from 'lucide-react';"
NEW_IMPORTS = "import { AlertTriangle, Check, ChevronDown, Clock, FlaskConical, PowerOff, Search, Wrench } from 'lucide-react';"

if OLD_IMPORTS not in content:
    print("ERROR: import anchor not found")
    exit(1)
content = content.replace(OLD_IMPORTS, NEW_IMPORTS)

# 2) Add helper function for partial badge after the capabilityHint function
PARTIAL_BADGE_FN = '''
function PartialStatusBadge({ tpl, t }: { tpl: RuleCatalogTemplate; t: (k: string, opts?: Record<string, unknown>) => string }) {
  const ps = tpl.partial_status;
  if (!ps || ps === 'full') return null;

  const cfg = {
    requires_calibration: {
      icon: <Wrench className="w-3 h-3 shrink-0" />,
      label: t('rules.partial.requires_calibration'),
      cls: 'text-amber-400 bg-amber-400/10 border-amber-400/30',
    },
    requires_ocr: {
      icon: <FlaskConical className="w-3 h-3 shrink-0" />,
      label: t('rules.partial.requires_ocr'),
      cls: 'text-violet-400 bg-violet-400/10 border-violet-400/30',
    },
    requires_face_ai: {
      icon: <FlaskConical className="w-3 h-3 shrink-0" />,
      label: t('rules.partial.requires_face_ai'),
      cls: 'text-violet-400 bg-violet-400/10 border-violet-400/30',
    },
    partial_aggregate: {
      icon: <AlertTriangle className="w-3 h-3 shrink-0" />,
      label: t('rules.partial.partial_aggregate'),
      cls: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30',
    },
  } as const;

  const item = cfg[ps as keyof typeof cfg];
  if (!item) return null;

  return (
    <span
      title={tpl.partial_reason_fr ?? item.label}
      className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded border ${item.cls}`}
    >
      {item.icon}
      {item.label}
    </span>
  );
}

'''

# Insert before RuleCard component
ANCHOR = "function RuleCard({"
if ANCHOR not in content:
    print("ERROR: RuleCard anchor not found")
    exit(1)
content = content.replace(ANCHOR, PARTIAL_BADGE_FN + ANCHOR)

# 3) Render the badge in RuleCard, after the supported badge
OLD_BADGE_LINE = "          {!isSupported && <span className=\"text-[10px] text-cv-muted bg-cv-surface px-1.5 py-0.5 rounded\">{t('rules.catalogCard.soonBadge')}</span>}"
NEW_BADGE_LINE = """          {!isSupported && <span className="text-[10px] text-cv-muted bg-cv-surface px-1.5 py-0.5 rounded">{t('rules.catalogCard.soonBadge')}</span>}
          {isSupported && <PartialStatusBadge tpl={tpl} t={t} />}"""

if OLD_BADGE_LINE not in content:
    print("ERROR: badge anchor not found in RuleCard")
    exit(1)
content = content.replace(OLD_BADGE_LINE, NEW_BADGE_LINE)

panel_file.write_text(content, encoding="utf-8")
print("Patched RuleCatalogPanel.tsx")
