#!/usr/bin/env node
/**
 * Downloads royalty-free guide photos (Pexels / Unsplash) into frontend/public/guides/rules/photos/
 * Run: node scripts/fetch-guide-photos.mjs
 */
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(__dirname, '../frontend/public/guides/rules/photos');

/** Curated Pexels photos — Pexels License (free use) */
const PHOTOS = [
  {
    category: 'default',
    url: 'https://images.pexels.com/photos/3395679/pexels-photo-3395679.jpeg?auto=compress&cs=tinysrgb&w=800',
    author: 'Pexels',
    license: 'Pexels License',
    sourceUrl: 'https://www.pexels.com/photo/security-camera-on-wall-3395679/',
    theme: 'Security camera on wall',
  },
  {
    category: 'quality',
    url: 'https://images.pexels.com/photos/442587/pexels-photo-442587.jpeg?auto=compress&cs=tinysrgb&w=800',
    author: 'Pexels',
    license: 'Pexels License',
    sourceUrl: 'https://www.pexels.com/photo/blur-night-street-442587/',
    theme: 'Blurry night CCTV-style view',
  },
  {
    category: 'behavior',
    url: 'https://images.pexels.com/photos/46798/the-boxer-sport-muay-thai-46798.jpeg?auto=compress&cs=tinysrgb&w=800',
    author: 'Pexels',
    license: 'Pexels License',
    sourceUrl: 'https://www.pexels.com/photo/man-boxing-46798/',
    theme: 'Altercation / fight',
  },
  {
    category: 'intrusion',
    url: 'https://images.pexels.com/photos/209315/pexels-photo-209315.jpeg?auto=compress&cs=tinysrgb&w=800',
    author: 'Pexels',
    license: 'Pexels License',
    sourceUrl: 'https://www.pexels.com/photo/chain-link-fence-209315/',
    theme: 'Perimeter fence',
  },
  {
    category: 'traffic',
    url: 'https://images.pexels.com/photos/3802510/pexels-photo-3802510.jpeg?auto=compress&cs=tinysrgb&w=800',
    author: 'Pexels',
    license: 'Pexels License',
    sourceUrl: 'https://www.pexels.com/photo/cars-on-road-during-daytime-3802510/',
    theme: 'Urban traffic',
  },
  {
    category: 'security',
    url: 'https://images.pexels.com/photos/60504/security-protection-anti-virus-software-60504.jpeg?auto=compress&cs=tinysrgb&w=800',
    author: 'Pexels',
    license: 'Pexels License',
    sourceUrl: 'https://www.pexels.com/photo/security-lock-on-computer-keyboard-60504/',
    theme: 'Security monitoring',
  },
  {
    category: 'presence',
    url: 'https://images.pexels.com/photos/3184418/pexels-photo-3184418.jpeg?auto=compress&cs=tinysrgb&w=800',
    author: 'Pexels',
    license: 'Pexels License',
    sourceUrl: 'https://www.pexels.com/photo/group-of-people-sitting-indoors-3184418/',
    theme: 'Crowd / meeting presence',
  },
  {
    category: 'speed',
    url: 'https://images.pexels.com/photos/3802510/pexels-photo-3802510.jpeg?auto=compress&cs=tinysrgb&w=800',
    author: 'Pexels',
    license: 'Pexels License',
    sourceUrl: 'https://www.pexels.com/photo/cars-on-road-during-daytime-3802510/',
    theme: 'Vehicle speed highway',
  },
  {
    category: 'extended',
    url: 'https://images.pexels.com/photos/1267338/pexels-photo-1267338.jpeg?auto=compress&cs=tinysrgb&w=800',
    author: 'Pexels',
    license: 'Pexels License',
    sourceUrl: 'https://www.pexels.com/photo/warehouse-with-boxes-1267338/',
    theme: 'Industrial warehouse',
  },
  {
    category: 'identity',
    url: 'https://images.pexels.com/photos/2379004/pexels-photo-2379004.jpeg?auto=compress&cs=tinysrgb&w=800',
    author: 'Pexels',
    license: 'Pexels License',
    sourceUrl: 'https://www.pexels.com/photo/man-in-black-suit-jacket-2379004/',
    theme: 'Face / identity portrait',
  },
  {
    category: 'crowd',
    url: 'https://images.pexels.com/photos/1763075/pexels-photo-1763075.jpeg?auto=compress&cs=tinysrgb&w=800',
    author: 'Pexels',
    license: 'Pexels License',
    sourceUrl: 'https://www.pexels.com/photo/people-at-concert-1763075/',
    theme: 'Large crowd',
  },
  {
    category: 'spatial',
    url: 'https://images.pexels.com/photos/1482803/pexels-photo-1482803.jpeg?auto=compress&cs=tinysrgb&w=800',
    author: 'Pexels',
    license: 'Pexels License',
    sourceUrl: 'https://www.pexels.com/photo/aerial-view-of-city-1482803/',
    theme: 'Aerial spatial view',
  },
  {
    category: 'road-enforcement',
    url: 'https://images.pexels.com/photos/3802510/pexels-photo-3802510.jpeg?auto=compress&cs=tinysrgb&w=800',
    author: 'Pexels',
    license: 'Pexels License',
    sourceUrl: 'https://www.pexels.com/photo/cars-on-road-during-daytime-3802510/',
    theme: 'Road enforcement',
  },
  {
    category: 'composite',
    url: 'https://images.pexels.com/photos/325111/pexels-photo-325111.jpeg?auto=compress&cs=tinysrgb&w=800',
    author: 'Pexels',
    license: 'Pexels License',
    sourceUrl: 'https://www.pexels.com/photo/server-rack-325111/',
    theme: 'Multi-signal monitoring',
  },
];

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  const attributions = [];

  for (const photo of PHOTOS) {
    const outPath = join(OUT_DIR, `${photo.category}.jpg`);
    try {
      const res = await fetch(photo.url, {
        headers: { 'User-Agent': 'CitevisionGuidePhotoFetcher/1.0' },
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const buf = Buffer.from(await res.arrayBuffer());
      await writeFile(outPath, buf);
      attributions.push({ ...photo, file: `${photo.category}.jpg` });
      console.log(`OK ${photo.category}.jpg`);
    } catch (e) {
      console.warn(`SKIP ${photo.category}: ${e.message ?? e}`);
    }
  }

  const readme = `# Rule guide photos

Realistic photos for the rule studio guide rail (Pexels License — free use).

| Category | File | Theme | Source |
|----------|------|-------|--------|
${attributions.map((a) => `| ${a.category} | \`${a.file}\` | ${a.theme} | [Pexels](${a.sourceUrl}) |`).join('\n')}

Regenerate: \`node scripts/fetch-guide-photos.mjs\`
`;
  await writeFile(join(dirname(OUT_DIR), 'README.md'), readme, 'utf8');
  console.log('Done — README updated');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
