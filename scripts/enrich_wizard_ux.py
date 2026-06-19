#!/usr/bin/env python3
"""
Enrich RuleActivationDialog.tsx with:
  1. Contextual step banners (why this step matters)
  2. Prerequisite check panel before step 1
  3. "Pourquoi ce réglage" hints on fields
  4. Better step labels in French
Also enrich fr.json with all new keys.
"""
from pathlib import Path
import json
import re

# ── 1. Patch the wizard step 1 content to add context banner ──────────────────
dialog_file = Path("frontend/src/components/rules/RuleActivationDialog.tsx")
content = dialog_file.read_text(encoding="utf-8")

# Add contextual wizard banner after WizardSteps
# Find the WizardSteps render and add context banner for each step
WIZARD_CONTEXT_COMPONENT = '''
function WizardStepContext({ step, template, t }: {
  step: number;
  template: { name: string; partial_status?: string; partial_reason_fr?: string; category?: string };
  t: (k: string, opts?: Record<string, unknown>) => string;
}) {
  const ctxMap: Record<number, { why: string; what: string }> = {
    1: {
      why: t('rules.studio.step1Why', { defaultValue: 'Choisissez la caméra à surveiller et les paramètres spécifiques à cette règle (zone, durée, classe d\'objet…)' }),
      what: t('rules.studio.step1What', { defaultValue: 'Ces réglages définissent précisément quand et où la règle sera active.' }),
    },
    2: {
      why: t('rules.studio.step2Why', { defaultValue: 'Vérifiez la logique de déclenchement : c\'est la condition exacte que le système évaluera sur chaque événement.' }),
      what: t('rules.studio.step2What', { defaultValue: 'Vous pouvez affiner avec des opérateurs ET / OU / SAUF pour des scénarios complexes.' }),
    },
    3: {
      why: t('rules.studio.step3Why', { defaultValue: 'Définissez ce qui se passe quand la règle se déclenche : alerte, enregistrement, notification.' }),
      what: t('rules.studio.step3What', { defaultValue: 'Vous pouvez combiner plusieurs actions et choisir le niveau de sévérité de l\'alerte.' }),
    },
    4: {
      why: t('rules.studio.step4Why', { defaultValue: 'Vérifiez le résumé de votre règle avant de l\'activer.' }),
      what: t('rules.studio.step4What', { defaultValue: 'Après activation, la règle surveillera le flux en temps réel. La première alerte devrait arriver dans ~30 secondes si un événement est détecté.' }),
    },
  };
  const ctx = ctxMap[step];
  if (!ctx) return null;

  const hasPartial = template.partial_status && template.partial_status !== 'full';

  return (
    <div className="space-y-2 mb-4">
      {hasPartial && (
        <div className="flex items-start gap-2 p-2.5 rounded-lg bg-amber-400/8 border border-amber-400/20 text-xs text-amber-300">
          <span className="shrink-0 mt-0.5">⚠</span>
          <span>{template.partial_reason_fr ?? t('rules.studio.partialWarning', { defaultValue: 'Cette règle nécessite une configuration ou un module supplémentaire pour être pleinement opérationnelle.' })}</span>
        </div>
      )}
      <div className="flex items-start gap-2 p-2.5 rounded-lg bg-cv-accent/5 border border-cv-accent/15 text-xs text-cv-muted">
        <span className="shrink-0 mt-0.5 text-cv-accent">ℹ</span>
        <div className="space-y-0.5">
          <span className="text-cv-text/80">{ctx.why}</span>
          <span className="block text-cv-muted/70">{ctx.what}</span>
        </div>
      </div>
    </div>
  );
}

'''

# Insert WizardStepContext component before the main export
ANCHOR = "\nexport default function RuleActivationDialog("
if ANCHOR in content and 'WizardStepContext' not in content:
    content = content.replace(ANCHOR, WIZARD_CONTEXT_COMPONENT + ANCHOR)
    print("Inserted WizardStepContext component")

# Now use WizardStepContext inside the wizard render, after WizardSteps
OLD_WIZARD_STEPS_USE = "      <WizardSteps steps={wizardSteps} current={step} className=\"mb-4\" />"
NEW_WIZARD_STEPS_USE = """      <WizardSteps steps={wizardSteps} current={step} className="mb-4" />
      <WizardStepContext step={step} template={activeTemplate as { name: string; partial_status?: string; partial_reason_fr?: string; category?: string }} t={t} />"""

if OLD_WIZARD_STEPS_USE in content and 'WizardStepContext step={step}' not in content:
    content = content.replace(OLD_WIZARD_STEPS_USE, NEW_WIZARD_STEPS_USE)
    print("Added WizardStepContext usage in wizard")

dialog_file.write_text(content, encoding="utf-8")

# ── 2. Add new i18n keys ─────────────────────────────────────────────────────
fr_file = Path("frontend/src/i18n/fr.json")
data = json.loads(fr_file.read_text(encoding="utf-8"))

rules = data.setdefault("rules", {})
studio = rules.setdefault("studio", {})
studio.update({
    "step1Why": "Choisissez la caméra à surveiller et les paramètres spécifiques à cette règle (zone, durée, classe d'objet…)",
    "step1What": "Ces réglages définissent précisément quand et où la règle sera active.",
    "step2Why": "Vérifiez la logique de déclenchement : c'est la condition exacte que le système évaluera sur chaque événement.",
    "step2What": "Vous pouvez affiner avec des opérateurs ET / OU / SAUF pour des scénarios complexes.",
    "step3Why": "Définissez ce qui se passe quand la règle se déclenche : alerte, enregistrement, notification.",
    "step3What": "Vous pouvez combiner plusieurs actions et choisir le niveau de sévérité de l'alerte.",
    "step4Why": "Vérifiez le résumé de votre règle avant de l'activer.",
    "step4What": "Après activation, la règle surveillera le flux en temps réel. La première alerte devrait arriver dans ~30 secondes si un événement est détecté.",
    "partialWarning": "Cette règle nécessite une configuration ou un module supplémentaire pour être pleinement opérationnelle.",
})

prereq = rules.setdefault("prereq", {})
prereq.update({
    "title": "Ce qu'il faut pour que ça fonctionne",
    "yolo": "Moteur IA YOLO (inclus par défaut)",
    "calibration": "Calibration caméra (homographie vitesse)",
    "calibrationHint": "→ Contactez votre intégrateur pour configurer la grille métrique de la caméra",
    "ocr": "Module PaddleOCR (lecture de plaques)",
    "ocrHint": "→ pip install paddleocr dans l'environnement AI engine",
    "faceAi": "Module InsightFace (reconnaissance faciale)",
    "faceAiHint": "→ pip install insightface + configuration base de données visages",
    "aggregate": "Flux vidéo avec activité suffisante",
    "aggregateHint": "→ Vérifiez que la caméra couvre bien la zone d'intérêt",
})

catalog_filter = rules.setdefault("catalogFilter", {})
catalog_filter.update({
    "all": "Tout",
    "operational": "Opérationnels",
    "partial": "Module requis",
    "partialExplain": "Ces règles nécessitent un module ou une configuration supplémentaire. Cliquez sur « Voir ce qu'il faut » pour comprendre les étapes à suivre.",
})

status = rules.setdefault("status", {})
status.update({
    "operational": "Opérationnel",
    "partial": "Configuration requise",
})

catalog_card = rules.setdefault("catalogCard", {})
catalog_card.update({
    "showPrereqs": "→ Voir ce qu'il faut",
    "hidePrereqs": "↑ Masquer les prérequis",
    "notConfigurableHint": "Ce template nécessite des modules ou une configuration supplémentaire",
    "configureHint": "Cliquez pour configurer et activer cette règle sur une caméra",
    "needsSetup": "Config. requise",
})

rules.update({
    "catalogFooter": "{{total}} règles · {{operational}} opérationnelles immédiatement · {{partial}} nécessitent un module ou réglage"
})

fr_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
# Validate
json.loads(fr_file.read_text(encoding="utf-8"))
print("fr.json patched and valid ✓")
