#!/usr/bin/env node
/**
 * Validates shared/catalog-navigation.json against rule-catalog templates.
 * Exit 1 on missing/extra mappings or invalid references.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CATALOG_DIR = join(ROOT, 'shared', 'rule-catalog');
const NAV_PATH = join(ROOT, 'shared', 'catalog-navigation.json');

function loadCatalogIds() {
  const ids = new Set();
  for (const name of readdirSync(CATALOG_DIR).filter((f) => f.endsWith('.json'))) {
    const batch = JSON.parse(readFileSync(join(CATALOG_DIR, name), 'utf8'));
    for (const t of batch) {
      if (t.redirect_to && !t.name) continue;
      if (t.id) ids.add(t.id);
    }
  }
  return ids;
}

function main() {
  const catalogIds = loadCatalogIds();
  const nav = JSON.parse(readFileSync(NAV_PATH, 'utf8'));
  const megaIds = new Set(nav.megaGroups.map((m) => m.id));
  const subById = new Map(nav.subGroups.map((s) => [s.id, s]));
  const navIds = new Set(Object.keys(nav.templates ?? {}));

  let errors = 0;

  for (const id of catalogIds) {
    if (!navIds.has(id)) {
      console.error(`[FAIL] Missing navigation for template: ${id}`);
      errors++;
    }
  }

  for (const id of navIds) {
    if (!catalogIds.has(id)) {
      console.error(`[FAIL] Unknown template in navigation: ${id}`);
      errors++;
    }
  }

  for (const [id, entry] of Object.entries(nav.templates ?? {})) {
    if (!megaIds.has(entry.megaId)) {
      console.error(`[FAIL] ${id}: invalid megaId "${entry.megaId}"`);
      errors++;
    }
    const sub = subById.get(entry.subId);
    if (!sub) {
      console.error(`[FAIL] ${id}: invalid subId "${entry.subId}"`);
      errors++;
    } else if (sub.megaId !== entry.megaId) {
      console.error(`[FAIL] ${id}: subId "${entry.subId}" belongs to mega "${sub.megaId}", not "${entry.megaId}"`);
      errors++;
    }
  }

  if (errors > 0) {
    console.error(`\n${errors} error(s). Run: node scripts/generate-catalog-navigation.mjs`);
    process.exit(1);
  }

  console.log(`[PASS] catalog-navigation.json — ${catalogIds.size} templates, ${nav.megaGroups.length} mega groups, ${nav.subGroups.length} sub groups`);
}

main();
