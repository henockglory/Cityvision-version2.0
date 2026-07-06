#!/usr/bin/env node
/**
 * Generates frontend/src/data/optionExplanations.ts from shared JSON sources.
 * Run: node scripts/generate-option-explanations.mjs
 */
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const OUT = join(ROOT, 'frontend/src/data/optionExplanations.ts');

const ai = JSON.parse(await readFile(join(ROOT, 'shared/ai-capabilities.json'), 'utf8'));
const classes = JSON.parse(await readFile(join(ROOT, 'shared/detection-classes.json'), 'utf8'));

const MODEL_LABELS = {
  yolo: 'YOLO (détection objets)',
  bytetrack: 'ByteTrack (suivi multi-objets)',
  ocr: 'OCR plaques',
  insightface: 'InsightFace (reconnaissance faciale)',
  paddleocr: 'PaddleOCR',
  heuristics: 'Heuristiques comportementales',
};

function technologyFromModels(models) {
  if (!models?.length) return 'Analyse heuristique / qualité image';
  return models.map((m) => MODEL_LABELS[m] ?? m.toUpperCase()).join(' + ');
}

function technologyFromModelsEn(models) {
  if (!models?.length) return 'Heuristic / image quality analysis';
  const en = { yolo: 'YOLO (object detection)', bytetrack: 'ByteTrack (multi-object tracking)', ocr: 'License plate OCR', insightface: 'InsightFace (face recognition)', paddleocr: 'PaddleOCR', heuristics: 'Behavior heuristics' };
  return models.map((m) => en[m] ?? m.toUpperCase()).join(' + ');
}

/** Merge template metadata by capability_id */
const templateByCapability = {};
for (const tpl of Object.values(ai.templates ?? {})) {
  const cid = tpl.capability_id;
  if (!cid || templateByCapability[cid]) continue;
  templateByCapability[cid] = tpl;
}

const eventTypesFr = {};
const eventTypesEn = {};

for (const [id, meta] of Object.entries(ai.event_types ?? {})) {
  const tpl = templateByCapability[id] ?? {};
  const prereq = Array.isArray(tpl.prerequisites) ? tpl.prerequisites.join(', ') : '';
  const humanDesc = tpl.human_description ?? meta.label_fr ?? id;
  const roleFr = tpl.role_summary_fr ?? `Déclenche une alerte lorsque l'événement « ${meta.label_fr ?? id} » est détecté.`;
  const roleEn = `Triggers an alert when « ${meta.label_en ?? meta.label_fr ?? id} » is detected on the stream.`;

  const howFr = prereq ? `${humanDesc} Prérequis : ${prereq}.` : humanDesc;
  const howEn = prereq ? `${humanDesc} Prerequisites: ${prereq}.` : humanDesc;

  eventTypesFr[id] = {
    label: meta.label_fr ?? id,
    technicalId: id,
    technology: technologyFromModels(meta.models),
    howItWorks: howFr,
    stepUtility: `À l'étape Conditions : ${roleFr}`,
  };
  eventTypesEn[id] = {
    label: meta.label_en ?? meta.label_fr ?? id,
    technicalId: id,
    technology: technologyFromModelsEn(meta.models),
    howItWorks: howEn,
    stepUtility: `At the Conditions step: ${roleEn}`,
  };
}

const CLASS_HINTS_FR = {
  person: { technology: 'YOLO classe COCO « person »', howItWorks: 'Détection de silhouettes humaines dans le flux vidéo.', stepUtility: 'Filtre les événements aux personnes uniquement.' },
  vehicle: { technology: 'YOLO — groupe car, truck, bus, motorcycle…', howItWorks: 'Regroupe les classes véhicules routiers COCO.', stepUtility: 'Limite la règle aux véhicules motorisés.' },
  bicycle: { technology: 'YOLO classe COCO « bicycle »', howItWorks: 'Détection de vélos et cyclistes.', stepUtility: 'Cible les déplacements à vélo dans la zone.' },
  animal: { technology: 'YOLO — oiseaux, chiens, chevaux…', howItWorks: 'Classes animales COCO (faune urbaine ou agricole).', stepUtility: 'Filtre les alertes sur la présence d\'animaux.' },
  baggage: { technology: 'YOLO — sac, valise, sac à dos', howItWorks: 'Objets laissés ou transportés (backpack, handbag, suitcase).', stepUtility: 'Détecte bagages abandonnés ou en mouvement.' },
  any: { technology: 'YOLO — toutes classes COCO', howItWorks: 'Aucun filtre de classe : tout objet détecté compte.', stepUtility: 'Condition la plus large pour capturer tout mouvement.' },
};

const CLASS_HINTS_EN = {
  person: { technology: 'YOLO COCO class « person »', howItWorks: 'Human silhouette detection in the video stream.', stepUtility: 'Filters events to people only.' },
  vehicle: { technology: 'YOLO — car, truck, bus, motorcycle group', howItWorks: 'Groups road vehicle COCO classes.', stepUtility: 'Limits the rule to motor vehicles.' },
  bicycle: { technology: 'YOLO COCO class « bicycle »', howItWorks: 'Bicycle and cyclist detection.', stepUtility: 'Targets bike movement in the zone.' },
  animal: { technology: 'YOLO — birds, dogs, horses…', howItWorks: 'Animal COCO classes.', stepUtility: 'Filters alerts for animal presence.' },
  baggage: { technology: 'YOLO — bag, suitcase, backpack', howItWorks: 'Carried or left objects.', stepUtility: 'Detects abandoned or moving baggage.' },
  any: { technology: 'YOLO — all COCO classes', howItWorks: 'No class filter — any detected object counts.', stepUtility: 'Broadest condition to capture any motion.' },
};

const COCO_HINTS_FR = {
  person: 'Silhouette humaine',
  car: 'Voiture particulière',
  truck: 'Camion / poids lourd',
  bus: 'Bus / transport en commun',
  motorcycle: 'Moto ou scooter',
  bicycle: 'Vélo',
  'traffic light': 'Feu tricolore (contexte routier)',
};

const classGroupsFr = {};
const classGroupsEn = {};
for (const g of classes.groups ?? []) {
  const hint = CLASS_HINTS_FR[g.id] ?? CLASS_HINTS_FR.any;
  classGroupsFr[g.id] = { label: g.label_fr, technicalId: g.id, ...hint };
  const hintEn = CLASS_HINTS_EN[g.id] ?? CLASS_HINTS_EN.any;
  classGroupsEn[g.id] = { label: g.label_en, technicalId: g.id, ...hintEn };
}

const cocoClassesFr = {};
const cocoClassesEn = {};
for (const c of classes.coco_classes ?? []) {
  const label = c;
  const desc = COCO_HINTS_FR[c] ?? `Classe COCO « ${c} » détectée par YOLO`;
  cocoClassesFr[c] = {
    label: c,
    technicalId: c,
    technology: 'YOLO détection COCO',
    howItWorks: desc,
    stepUtility: `Filtre précis sur la classe « ${c} » pour affiner la condition.`,
  };
  cocoClassesEn[c] = {
    label: c,
    technicalId: c,
    technology: 'YOLO COCO detection',
    howItWorks: COCO_HINTS_FR[c] ? desc : `COCO class « ${c} » detected by YOLO`,
    stepUtility: `Precise filter on class « ${c} » to refine the condition.`,
  };
}

const directionsFr = {
  both: { label: 'Les deux sens', technology: 'Comptage bidirectionnel', howItWorks: 'Franchissements comptés dans les deux directions.', stepUtility: 'Utile pour flux mixtes entrée/sortie.' },
  in: { label: 'Entrée', technology: 'Capteur directionnel', howItWorks: 'Objets entrant dans la zone ou franchissant la ligne vers l\'intérieur.', stepUtility: 'Alerte uniquement sur les entrées.' },
  out: { label: 'Sortie', technology: 'Capteur directionnel', howItWorks: 'Objets quittant la zone ou sortant par la ligne.', stepUtility: 'Alerte uniquement sur les sorties.' },
  left: { label: 'Gauche', technology: 'Vecteur de déplacement', howItWorks: 'Mouvement vers la gauche dans le repère caméra.', stepUtility: 'Filtrage directionnel gauche.' },
  right: { label: 'Droite', technology: 'Vecteur de déplacement', howItWorks: 'Mouvement vers la droite dans le repère caméra.', stepUtility: 'Filtrage directionnel droite.' },
  unknown: { label: 'Inconnu', technology: 'Direction non calculée', howItWorks: 'Direction absente ou non fiable.', stepUtility: 'Accepte tout franchissement sans filtre directionnel.' },
};

const directionsEn = {
  both: { label: 'Both directions', technology: 'Bidirectional counting', howItWorks: 'Crossings counted in both directions.', stepUtility: 'For mixed in/out traffic flows.' },
  in: { label: 'In', technology: 'Directional sensor', howItWorks: 'Objects entering the zone or crossing inward.', stepUtility: 'Alerts on entries only.' },
  out: { label: 'Out', technology: 'Directional sensor', howItWorks: 'Objects leaving the zone or crossing outward.', stepUtility: 'Alerts on exits only.' },
  left: { label: 'Left', technology: 'Movement vector', howItWorks: 'Movement to the left in camera frame.', stepUtility: 'Left directional filter.' },
  right: { label: 'Right', technology: 'Movement vector', howItWorks: 'Movement to the right in camera frame.', stepUtility: 'Right directional filter.' },
  unknown: { label: 'Unknown', technology: 'Direction not computed', howItWorks: 'Direction missing or unreliable.', stepUtility: 'Accepts any crossing without direction filter.' },
};

for (const d of Object.keys(directionsFr)) {
  directionsFr[d].technicalId = d;
  directionsEn[d].technicalId = d;
}

const ts = `/** Auto-generated — do not edit. Run: node scripts/generate-option-explanations.mjs */

export interface ExplanatoryOptionMeta {
  label: string;
  technicalId: string;
  technology: string;
  howItWorks: string;
  stepUtility: string;
  group?: string;
}

export const eventTypeExplanations = {
  fr: ${JSON.stringify(eventTypesFr, null, 2)} as Record<string, ExplanatoryOptionMeta>,
  en: ${JSON.stringify(eventTypesEn, null, 2)} as Record<string, ExplanatoryOptionMeta>,
};

export const classGroupExplanations = {
  fr: ${JSON.stringify(classGroupsFr, null, 2)} as Record<string, ExplanatoryOptionMeta>,
  en: ${JSON.stringify(classGroupsEn, null, 2)} as Record<string, ExplanatoryOptionMeta>,
};

export const cocoClassExplanations = {
  fr: ${JSON.stringify(cocoClassesFr, null, 2)} as Record<string, ExplanatoryOptionMeta>,
  en: ${JSON.stringify(cocoClassesEn, null, 2)} as Record<string, ExplanatoryOptionMeta>,
};

export const directionExplanations = {
  fr: ${JSON.stringify(directionsFr, null, 2)} as Record<string, ExplanatoryOptionMeta>,
  en: ${JSON.stringify(directionsEn, null, 2)} as Record<string, ExplanatoryOptionMeta>,
};
`;

await writeFile(OUT, ts, 'utf8');
console.log(`Wrote ${OUT}`);
