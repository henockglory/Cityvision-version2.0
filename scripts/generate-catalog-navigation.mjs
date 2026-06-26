#!/usr/bin/env node
/**
 * Generates shared/catalog-navigation.json from rule-catalog templates.
 * Run: node scripts/generate-catalog-navigation.mjs
 */
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CATALOG_DIR = join(ROOT, 'shared', 'rule-catalog');
const OUT = join(ROOT, 'shared', 'catalog-navigation.json');

const MEGA_GROUPS = [
  {
    id: 'places',
    order: 1,
    scopeOrder: { all: 1, enterprise: 1, domestic: 1, national: 2 },
  },
  {
    id: 'people',
    order: 2,
    scopeOrder: { all: 2, enterprise: 2, domestic: 2, national: 3 },
  },
  {
    id: 'road',
    order: 3,
    scopeOrder: { all: 3, enterprise: 4, domestic: 6, national: 1 },
  },
  {
    id: 'identity',
    order: 4,
    scopeOrder: { all: 4, enterprise: 3, domestic: 4, national: 4 },
  },
  {
    id: 'objects',
    order: 5,
    scopeOrder: { all: 5, enterprise: 5, domestic: 3, national: 5 },
  },
  {
    id: 'camera',
    order: 6,
    scopeOrder: { all: 6, enterprise: 6, domestic: 5, national: 6 },
    muted: true,
  },
];

const SUB_GROUPS = [
  { id: 'intrusion', megaId: 'places', order: 1 },
  { id: 'zones', megaId: 'places', order: 2 },
  { id: 'passages', megaId: 'places', order: 3 },
  { id: 'presence', megaId: 'people', order: 1 },
  { id: 'gestures', megaId: 'people', order: 2 },
  { id: 'crowd', megaId: 'people', order: 3 },
  { id: 'speed', megaId: 'road', order: 1 },
  { id: 'traffic', megaId: 'road', order: 2 },
  { id: 'road_infractions', megaId: 'road', order: 3 },
  { id: 'faces', megaId: 'identity', order: 1 },
  { id: 'plates', megaId: 'identity', order: 2 },
  { id: 'objects_scene', megaId: 'objects', order: 1 },
  { id: 'emergencies', megaId: 'objects', order: 2 },
  { id: 'image_quality', megaId: 'camera', order: 1 },
  { id: 'schedules', megaId: 'camera', order: 2 },
  { id: 'industrial_site', megaId: 'camera', order: 3 },
];

/** Explicit overrides — highest priority */
const OVERRIDES = {
  'tpl-industrial-intrusion': { megaId: 'camera', subId: 'industrial_site', searchTags: ['industriel', 'usine', 'site'] },
  'tpl-loitering': { megaId: 'camera', subId: 'schedules', searchTags: ['loitering', ' présence prolongée', 'durée'] },
  'tpl-dwell-exceeded': { megaId: 'camera', subId: 'schedules', searchTags: ['durée', 'temps', 'présence'] },
  'tpl-loitering-entrance': { megaId: 'places', subId: 'intrusion', searchTags: ['entrée', 'flânerie'] },
  'tpl-tailgating': { megaId: 'places', subId: 'passages', searchTags: ['tailgating', 'suivi', 'accès'] },
  'tpl-wrong-way': { megaId: 'road', subId: 'traffic', searchTags: ['sens interdit', 'contre-sens'] },
  'tpl-vehicle-count': { megaId: 'road', subId: 'traffic', searchTags: ['véhicules', 'comptage', 'trafic'] },
  'tpl-vehicle-stopped': { megaId: 'road', subId: 'traffic', searchTags: ['véhicule arrêté', 'stationné'] },
  'tpl-scene-occupancy': { megaId: 'people', subId: 'presence', searchTags: ['occupation', 'scène'] },
  'tpl-running-person': { megaId: 'people', subId: 'gestures', searchTags: ['course', 'fuite'] },
  'tpl-fight': { megaId: 'objects', subId: 'emergencies', searchTags: ['bagarre', 'violence'] },
  'tpl-fighting': { megaId: 'people', subId: 'gestures', searchTags: ['bagarre', 'violence'] },
  'tpl-accident-composite': { megaId: 'objects', subId: 'emergencies', searchTags: ['accident', 'collision'] },
  'tpl-accident': { megaId: 'objects', subId: 'emergencies', searchTags: ['accident', 'collision'] },
};

const CROWD_IDS = new Set([
  'tpl-crowd-count',
  'tpl-crowd-density',
  'tpl-crowd-gathering',
  'tpl-crowd-panic',
  'tpl-group-formation',
  'tpl-queue-forming',
  'tpl-bottleneck',
  'tpl-flow-rate',
]);

function loadTemplates() {
  const byId = new Map();
  for (const name of readdirSync(CATALOG_DIR).filter((f) => f.endsWith('.json')).sort()) {
    const batch = JSON.parse(readFileSync(join(CATALOG_DIR, name), 'utf8'));
    for (const t of batch) {
      if (t.redirect_to && !t.name) continue;
      if (!t.id || byId.has(t.id)) continue;
      byId.set(t.id, t);
    }
  }
  return byId;
}

function inferNav(tpl) {
  const id = tpl.id;
  const cat = tpl.category ?? 'other';

  if (OVERRIDES[id]) return { ...OVERRIDES[id] };

  if (CROWD_IDS.has(id) || cat === 'crowd') {
    return { megaId: 'people', subId: 'crowd', searchTags: tagsFromName(tpl.name, ['foule', 'attroupement']) };
  }

  if (cat === 'quality') {
    return { megaId: 'camera', subId: 'image_quality', searchTags: tagsFromName(tpl.name, ['caméra', 'image']) };
  }
  if (cat === 'time') {
    return { megaId: 'camera', subId: 'schedules', searchTags: tagsFromName(tpl.name, ['horaire', 'durée']) };
  }
  if (cat === 'industrial') {
    return { megaId: 'camera', subId: 'industrial_site', searchTags: ['industriel'] };
  }

  if (cat === 'speed') {
    return { megaId: 'road', subId: 'speed', searchTags: tagsFromName(tpl.name, ['vitesse', 'km/h']) };
  }
  if (cat === 'traffic') {
    return { megaId: 'road', subId: 'traffic', searchTags: tagsFromName(tpl.name, ['trafic', 'circulation', 'véhicule']) };
  }
  if (cat === 'road-enforcement') {
    return { megaId: 'road', subId: 'road_infractions', searchTags: tagsFromName(tpl.name, ['infraction', 'route', 'feu']) };
  }

  if (cat === 'identity') {
    const subId = id.includes('plate') || id.includes('Plate') ? 'plates' : 'faces';
    return { megaId: 'identity', subId, searchTags: tagsFromName(tpl.name, subId === 'plates' ? ['plaque', 'ANPR'] : ['visage', 'identité']) };
  }

  if (cat === 'composite' || cat === 'incident') {
    return { megaId: 'objects', subId: 'emergencies', searchTags: tagsFromName(tpl.name, ['urgence', 'incident']) };
  }

  if (cat === 'objects') {
    return { megaId: 'objects', subId: 'objects_scene', searchTags: tagsFromName(tpl.name, ['objet', 'abandonné']) };
  }

  if (cat === 'presence') {
    return { megaId: 'people', subId: 'presence', searchTags: tagsFromName(tpl.name, ['présence', 'zone', 'errance']) };
  }

  if (cat === 'spatial') {
    if (id.includes('line-cross') || id.includes('wrong-direction') || id.includes('unauthorized-exit')) {
      return { megaId: 'places', subId: 'passages', searchTags: tagsFromName(tpl.name, ['ligne', 'franchissement', 'passage']) };
    }
    return { megaId: 'places', subId: 'zones', searchTags: tagsFromName(tpl.name, ['zone', 'périmètre', 'spatial']) };
  }

  if (cat === 'security') {
    return { megaId: 'places', subId: 'intrusion', searchTags: tagsFromName(tpl.name, ['intrusion', 'sécurité', 'accès']) };
  }

  if (cat === 'behavior') {
    return { megaId: 'people', subId: 'gestures', searchTags: tagsFromName(tpl.name, ['comportement', 'geste']) };
  }

  return { megaId: 'objects', subId: 'objects_scene', searchTags: tagsFromName(tpl.name, []) };
}

function tagsFromName(name = '', extra = []) {
  const base = (name ?? '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .split(/[^a-z0-9]+/)
    .filter((w) => w.length > 2);
  return [...new Set([...extra, ...base])].slice(0, 8);
}

function main() {
  const templates = loadTemplates();
  const navTemplates = {};
  for (const [id, tpl] of templates) {
    navTemplates[id] = inferNav(tpl);
  }

  const out = {
    version: 1,
    megaGroups: MEGA_GROUPS,
    subGroups: SUB_GROUPS,
    templates: navTemplates,
  };

  writeFileSync(OUT, `${JSON.stringify(out, null, 2)}\n`, 'utf8');
  console.log(`[OK] Wrote ${OUT} (${templates.size} templates)`);
}

main();
