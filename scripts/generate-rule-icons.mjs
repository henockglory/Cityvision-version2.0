/**
 * Generates distinct SVG icons per rule template id.
 * Run: node scripts/generate-rule-icons.mjs
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const catalogDir = path.join(__dirname, '../shared/rule-catalog');
const outDir = path.join(__dirname, '../frontend/public/icons/rules');

const SHAPES = ['circle', 'square', 'triangle', 'diamond', 'hex', 'star', 'cross', 'ring'];
const PALETTE = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#ec4899', '#84cc16'];

function hash(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

function shapeSvg(shape, color, cx, cy, r) {
  switch (shape) {
    case 'circle':
      return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}" opacity="0.9"/>`;
    case 'square':
      return `<rect x="${cx - r}" y="${cy - r}" width="${r * 2}" height="${r * 2}" rx="4" fill="${color}" opacity="0.9"/>`;
    case 'triangle':
      return `<polygon points="${cx},${cy - r} ${cx - r},${cy + r} ${cx + r},${cy + r}" fill="${color}" opacity="0.9"/>`;
    case 'diamond':
      return `<polygon points="${cx},${cy - r} ${cx + r},${cy} ${cx},${cy + r} ${cx - r},${cy}" fill="${color}" opacity="0.9"/>`;
    case 'hex':
      return `<polygon points="${cx},${cy - r} ${cx + r * 0.86},${cy - r * 0.5} ${cx + r * 0.86},${cy + r * 0.5} ${cx},${cy + r} ${cx - r * 0.86},${cy + r * 0.5} ${cx - r * 0.86},${cy - r * 0.5}" fill="${color}" opacity="0.9"/>`;
    case 'star':
      return `<polygon points="${cx},${cy - r} ${cx + r * 0.3},${cy - r * 0.3} ${cx + r},${cy - r * 0.3} ${cx + r * 0.45},${cy + r * 0.15} ${cx + r * 0.6},${cy + r} ${cx},${cy + r * 0.45} ${cx - r * 0.6},${cy + r} ${cx - r * 0.45},${cy + r * 0.15} ${cx - r},${cy - r * 0.3} ${cx - r * 0.3},${cy - r * 0.3}" fill="${color}" opacity="0.9"/>`;
    case 'cross':
      return `<path d="M${cx - r * 0.35} ${cy - r} h${r * 0.7} v${r * 0.65} h${r} v${r * 0.7} h-${r * 0.7} v${r} h-${r * 0.7} v-${r} h-${r} v-${r * 0.7} z" fill="${color}" opacity="0.9"/>`;
    default:
      return `<circle cx="${cx}" cy="${cy}" r="${r * 0.75}" fill="none" stroke="${color}" stroke-width="3" opacity="0.9"/><circle cx="${cx}" cy="${cy}" r="${r * 0.35}" fill="${color}" opacity="0.9"/>`;
  }
}

function makeIcon(id) {
  const h = hash(id);
  const shape = SHAPES[h % SHAPES.length];
  const color = PALETTE[(h >> 3) % PALETTE.length];
  const accent = PALETTE[(h >> 7) % PALETTE.length];
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="12" fill="#0c1424" opacity="0.6"/>
  ${shapeSvg(shape, color, 32, 30, 14)}
  <circle cx="48" cy="16" r="5" fill="${accent}" opacity="0.85"/>
</svg>`;
}

const ids = new Set();
for (const file of fs.readdirSync(catalogDir)) {
  if (!file.endsWith('.json')) continue;
  const data = JSON.parse(fs.readFileSync(path.join(catalogDir, file), 'utf8'));
  const items = Array.isArray(data) ? data : data.templates ?? [];
  for (const t of items) {
    if (t?.id?.startsWith('tpl-')) ids.add(t.id);
  }
}

fs.mkdirSync(outDir, { recursive: true });
for (const id of ids) {
  fs.writeFileSync(path.join(outDir, `${id}.svg`), makeIcon(id));
}
console.log(`Generated ${ids.size} rule icons in ${outDir}`);
