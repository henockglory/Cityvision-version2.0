#!/usr/bin/env node
/**
 * Merges rules.narrative.events.* from shared/ai-capabilities.json into fr.json / en.json.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const CAPS = JSON.parse(
  fs.readFileSync(path.join(ROOT, 'shared', 'ai-capabilities.json'), 'utf8'),
);
const I18N_DIR = path.join(ROOT, 'frontend', 'src', 'i18n');

function buildEvents(lang) {
  const out = {};
  for (const [key, meta] of Object.entries(CAPS.event_types ?? {})) {
    const label =
      lang === 'fr'
        ? meta.label_fr ?? key
        : meta.label_en ?? meta.label_fr ?? key.replace(/_/g, ' ');
    out[key] = label;
  }
  return out;
}

for (const lang of ['fr', 'en']) {
  const file = path.join(I18N_DIR, `${lang}.json`);
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (!data.rules?.narrative) {
    console.error(`[SKIP] ${lang}.json missing rules.narrative`);
    continue;
  }
  data.rules.narrative.events = buildEvents(lang);
  fs.writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`);
  console.log(`[OK] ${lang}.json — ${Object.keys(data.rules.narrative.events).length} event labels`);
}
