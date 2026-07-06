#!/usr/bin/env node
/**
 * Generates rules.guides.* i18n stubs for every template in shared/rule-catalog.
 * Output: frontend/src/i18n/generated/rule-guides-fr.json, rule-guides-en.json
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const CATALOG_DIR = path.join(ROOT, 'shared', 'rule-catalog');
const OUT_DIR = path.join(ROOT, 'frontend', 'src', 'i18n', 'generated');

const CATEGORY_FR = {
  behavior: 'comportement',
  intrusion: 'intrusion',
  traffic: 'trafic',
  identity: 'identité',
  crowd: 'foule',
  'road-enforcement': 'route et infractions',
  spatial: 'spatial',
  security: 'sécurité',
  presence: 'présence',
  speed: 'vitesse',
  extended: 'étendu',
  composite: 'composite',
  'spatial-crossing': 'franchissement',
};

function loadTemplates() {
  const files = fs.readdirSync(CATALOG_DIR).filter((f) => f.endsWith('.json'));
  const all = [];
  for (const file of files) {
    const raw = JSON.parse(fs.readFileSync(path.join(CATALOG_DIR, file), 'utf8'));
    if (Array.isArray(raw)) all.push(...raw);
  }
  return all.filter((t) => t.id);
}

function leafHints(def) {
  const cond = def?.condition;
  if (!cond) return { event: 'event', field: 'condition' };
  if (cond.field === 'event_type') return { event: String(cond.value ?? 'event'), field: 'event_type' };
  return { event: String(cond.field ?? 'event'), field: String(cond.field ?? 'field') };
}

function buildGuideFr(tpl) {
  const cat = CATEGORY_FR[tpl.category] ?? tpl.category;
  const { event } = leafHints(tpl.definition);
  const name = tpl.name;
  const summary = tpl.role_summary_fr ?? tpl.description_fr ?? name;

  return {
    step1: {
      title: `Configurer « ${name} »`,
      body: `${summary} Choisissez la caméra qui couvre la zone concernée et les paramètres (zone, durée, objet…) adaptés à un site type « Entrée principale » ou « Parking ».`,
      checklist: [
        'Sélectionner une caméra en ligne avec un flux RTSP stable',
        'Dessiner ou choisir la zone / ligne si la règle est spatialisée',
        'Ajuster durée ou seuils selon la sensibilité souhaitée',
      ],
      tips: [
        `Catégorie : ${cat}.`,
        'Préférez un cadrage large et une bonne luminosité pour limiter les faux positifs.',
      ],
    },
    step2: {
      title: 'Logique de déclenchement',
      body: `Vérifiez que la condition correspond à votre intention : ${summary.toLowerCase()}`,
      checklist: [
        'Lire la phrase en français sous chaque condition',
        'Utiliser ET si toutes les conditions doivent être vraies simultanément',
        'Utiliser OU pour plusieurs scénarios indépendants',
      ],
      tips: ['Ouvrez « Voir des exemples » pour tester des cas concrets.'],
    },
    step3: {
      title: 'Actions et preuves',
      body: 'Définissez l’alerte, les preuves vidéo et les notifications (e-mail, webhook).',
      checklist: [
        'Choisir la sévérité (faible → critique)',
        'Activer clip + images si une preuve est nécessaire',
        'Optionnel : e-mail ou automatisation n8n/Make',
      ],
      tips: ['Un clip de 6 s suffit en général pour comprendre la situation.'],
    },
    step4: {
      title: 'Aperçu final',
      body: 'Relisez le résumé et le flux visuel avant d’activer la règle.',
      checklist: [
        'Confirmer caméra et zone dans le résumé',
        'Vérifier le flux conditions → actions',
        'Activer — première alerte sous ~30 s si un événement correspond',
      ],
      tips: [],
    },
    useCases: [
      {
        title: `Cas type — ${name}`,
        body: `Sur un site avec « Entrée principale », cette règle ${summary.toLowerCase()}`,
      },
      {
        title: 'Réglage recommandé',
        body: 'Commencez avec une sensibilité moyenne, puis ajustez après 24 h d’observation des alertes.',
      },
    ],
    scenarios: buildScenarios(tpl, event, 'fr'),
    whyYes: 'Les conditions de la règle sont remplies pour cet événement.',
    whyNo: 'Au moins une condition n\'est pas remplie — pas d\'alerte.',
  };
}

function buildGuideEn(tpl) {
  const name = tpl.name;
  const summary = tpl.role_summary_en ?? tpl.description_en ?? tpl.role_summary_fr ?? name;

  return {
    step1: {
      title: `Configure "${name}"`,
      body: `${summary} Pick a camera covering the area and set zone, duration, or object filters using neutral examples like "Main entrance" or "Parking".`,
      checklist: [
        'Select an online camera with a stable RTSP stream',
        'Draw or pick zone / line when spatial',
        'Tune duration or thresholds for desired sensitivity',
      ],
      tips: ['Prefer wide field of view and good lighting to reduce false positives.'],
    },
    step2: {
      title: 'Trigger logic',
      body: `Ensure the condition tree matches your intent: ${summary.toLowerCase()}`,
      checklist: [
        'Read the plain-language sentence under each condition',
        'Use AND when all conditions must match at once',
        'Use OR for independent scenarios',
      ],
      tips: ['Open "See examples" to test concrete cases.'],
    },
    step3: {
      title: 'Actions & evidence',
      body: 'Set alert severity, video evidence, and optional notifications.',
      checklist: ['Pick severity', 'Enable clip + snapshots if needed', 'Optional email or webhook'],
      tips: ['A 6 s clip is usually enough for context.'],
    },
    step4: {
      title: 'Final preview',
      body: 'Review the summary and visual flow before activating.',
      checklist: ['Confirm camera and zone', 'Check conditions → actions flow', 'Activate the rule'],
      tips: [],
    },
    useCases: [
      { title: `Typical case — ${name}`, body: summary },
      { title: 'Recommended tuning', body: 'Start medium sensitivity, adjust after 24 h of alerts.' },
    ],
    scenarios: buildScenarios(tpl, leafHints(tpl.definition).event, 'en'),
    whyYes: 'Rule conditions are satisfied for this event.',
    whyNo: 'At least one condition is not met — no alert.',
  };
}

function buildScenarios(tpl, event, lang) {
  const id = tpl.id;
  if (id === 'tpl-fighting') {
    return lang === 'fr'
      ? [
          {
            id: 'fight-yes',
            label: 'Deux personnes en interaction violente détectée',
            payload: { event_type: 'fighting', class_name: 'person' },
            whyKey: `rules.guides.${id}.whyYes`,
          },
          {
            id: 'fight-no',
            label: 'Une personne seule qui marche normalement',
            payload: { event_type: 'zone_presence', class_name: 'person' },
            whyKey: `rules.guides.${id}.whyNo`,
          },
        ]
      : [
          {
            id: 'fight-yes',
            label: 'Two people in violent interaction',
            payload: { event_type: 'fighting', class_name: 'person' },
            whyKey: `rules.guides.${id}.whyYes`,
          },
          {
            id: 'fight-no',
            label: 'Single person walking normally',
            payload: { event_type: 'zone_presence', class_name: 'person' },
            whyKey: `rules.guides.${id}.whyNo`,
          },
        ];
  }

  const matchPayload = { event_type: event };
  const missPayload = { event_type: 'other_event' };
  return lang === 'fr'
    ? [
        {
          id: 'yes',
          label: `Situation conforme (${event})`,
          payload: matchPayload,
          whyKey: `rules.guides.${id}.whyYes`,
        },
        {
          id: 'no',
          label: 'Autre type d’événement',
          payload: missPayload,
          whyKey: `rules.guides.${id}.whyNo`,
        },
      ]
    : [
        {
          id: 'yes',
          label: `Matching situation (${event})`,
          payload: matchPayload,
          whyKey: `rules.guides.${id}.whyYes`,
        },
        {
          id: 'no',
          label: 'Different event type',
          payload: missPayload,
          whyKey: `rules.guides.${id}.whyNo`,
        },
      ];
}

const templates = loadTemplates();
const guidesFr = {};
const guidesEn = {};

for (const tpl of templates) {
  guidesFr[tpl.id] = buildGuideFr(tpl);
  guidesEn[tpl.id] = buildGuideEn(tpl);
}

fs.mkdirSync(OUT_DIR, { recursive: true });
fs.writeFileSync(path.join(OUT_DIR, 'rule-guides-fr.json'), JSON.stringify(guidesFr, null, 2));
fs.writeFileSync(path.join(OUT_DIR, 'rule-guides-en.json'), JSON.stringify(guidesEn, null, 2));
console.log(`[OK] Generated guides for ${templates.length} templates → ${OUT_DIR}`);
