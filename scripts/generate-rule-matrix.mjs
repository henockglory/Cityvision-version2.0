#!/usr/bin/env node
// Generates an honest capability matrix for every rule-catalog template.
//
// Reads shared/rule-catalog/*.json and classifies each template as:
//   - real        : fully operational with the default stack (YOLO + tracking)
//   - partial     : works but needs an extra step (calibration, OCR, face AI,
//                   secondary ONNX model, on-site validation, or heuristic beta)
//   - unsupported : present in the catalog but not wired end-to-end
//
// Outputs:
//   shared/rule-capability-matrix.json  (machine-readable, source of truth)
//   docs/rule-honesty-matrix.md         (human-readable table)
//
// Run: node scripts/generate-rule-matrix.mjs

import { readFileSync, writeFileSync, readdirSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const catalogDir = join(root, 'shared', 'rule-catalog');

const PARTIAL_LABELS = {
  requires_calibration: 'Calibration caméra requise (homographie/vitesse)',
  requires_ocr: 'Module ANPR/PaddleOCR requis',
  requires_face_ai: 'Module InsightFace requis',
  requires_model: 'Modèle ONNX spécialisé requis',
  partial_aggregate: 'À valider sur site (données agrégées)',
  beta: 'Heuristique bêta — fiabilité variable',
};

function classify(tpl) {
  if (tpl.supported === false) {
    return { status: 'unsupported', reason: tpl.partial_reason_fr ?? 'Non câblé de bout en bout.' };
  }
  const ps = tpl.partial_status;
  if (!ps || ps === 'full') {
    return { status: 'real', reason: '' };
  }
  return {
    status: 'partial',
    reason: tpl.partial_reason_fr ?? PARTIAL_LABELS[ps] ?? ps,
    requirement: ps,
  };
}

const files = readdirSync(catalogDir).filter((f) => f.endsWith('.json'));
const entries = [];
for (const f of files) {
  const raw = JSON.parse(readFileSync(join(catalogDir, f), 'utf8'));
  const list = Array.isArray(raw) ? raw : [raw];
  for (const tpl of list) {
    if (!tpl.id) continue;
    // Skip pure redirect aliases (no name/definition of their own).
    if (tpl.redirect_to && !tpl.name) continue;
    const c = classify(tpl);
    entries.push({
      id: tpl.id,
      name: tpl.name ?? tpl.id,
      category: tpl.category ?? f.replace('.json', ''),
      status: c.status,
      requirement: c.requirement ?? null,
      reason: c.reason ?? '',
      event_type: tpl?.definition?.condition?.value ?? null,
    });
  }
}

entries.sort((a, b) => a.category.localeCompare(b.category) || a.name.localeCompare(b.name));

const counts = entries.reduce(
  (acc, e) => ((acc[e.status] = (acc[e.status] ?? 0) + 1), acc),
  {},
);

const matrix = {
  generated_at: new Date().toISOString(),
  total: entries.length,
  counts,
  templates: entries,
};

writeFileSync(
  join(root, 'shared', 'rule-capability-matrix.json'),
  JSON.stringify(matrix, null, 2) + '\n',
);

// Markdown report.
const docsDir = join(root, 'docs');
if (!existsSync(docsDir)) mkdirSync(docsDir, { recursive: true });

const badge = { real: '🟢 Réel', partial: '🟡 Partiel', unsupported: '🔴 Non supporté' };
let md = `# Matrice d'honnêteté des règles CitéVision\n\n`;
md += `> Généré automatiquement par \`scripts/generate-rule-matrix.mjs\` — ne pas éditer à la main.\n\n`;
md += `**Total : ${matrix.total} templates** — `;
md += `🟢 ${counts.real ?? 0} réels · 🟡 ${counts.partial ?? 0} partiels · 🔴 ${counts.unsupported ?? 0} non supportés.\n\n`;
md += `| Catégorie | Règle | Statut | Pré-requis / Raison |\n`;
md += `|-----------|-------|--------|----------------------|\n`;
for (const e of entries) {
  const reason = (e.reason || '—').replace(/\|/g, '\\|');
  md += `| ${e.category} | ${e.name} | ${badge[e.status]} | ${reason} |\n`;
}
md += `\n## Légende\n\n`;
md += `- **🟢 Réel** : fonctionne immédiatement avec le moteur par défaut (YOLOv8 + tracking).\n`;
md += `- **🟡 Partiel** : fonctionne après une étape supplémentaire (calibration, ANPR, modèle ONNX, reconnaissance faciale) ou détection heuristique « bêta ».\n`;
md += `- **🔴 Non supporté** : présent au catalogue mais pas câblé de bout en bout.\n`;

writeFileSync(join(docsDir, 'rule-honesty-matrix.md'), md);

console.log(
  `Matrix: ${matrix.total} templates → real=${counts.real ?? 0}, partial=${counts.partial ?? 0}, unsupported=${counts.unsupported ?? 0}`,
);
console.log('Wrote shared/rule-capability-matrix.json and docs/rule-honesty-matrix.md');
