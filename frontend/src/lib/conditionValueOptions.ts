import aiCapabilities from '@shared/ai-capabilities.json';
import type { ExplanatoryOption } from '@/components/ui/ExplanatorySelect';
import {
  classGroupExplanations,
  cocoClassExplanations,
  directionExplanations,
  eventTypeExplanations,
  type ExplanatoryOptionMeta,
} from '@/data/optionExplanations';

export type EventTypeOption = { value: string; labelFr: string };

const eventTypesRaw = aiCapabilities.event_types as Record<string, { label_fr?: string; label_en?: string }>;

export const EVENT_TYPE_OPTIONS: EventTypeOption[] = Object.entries(eventTypesRaw)
  .map(([value, meta]) => ({
    value,
    labelFr: meta.label_fr ?? value,
  }))
  .sort((a, b) => a.labelFr.localeCompare(b.labelFr, 'fr'));

export const DIRECTION_OPTIONS = [
  { value: 'both', labelFr: 'Les deux sens', labelEn: 'Both directions' },
  { value: 'in', labelFr: 'Entrée', labelEn: 'In' },
  { value: 'out', labelFr: 'Sortie', labelEn: 'Out' },
  { value: 'left', labelFr: 'Gauche', labelEn: 'Left' },
  { value: 'right', labelFr: 'Droite', labelEn: 'Right' },
  { value: 'unknown', labelFr: 'Inconnu', labelEn: 'Unknown' },
] as const;

function metaToOption(value: string, meta: ExplanatoryOptionMeta, group?: string): ExplanatoryOption {
  return { value, ...meta, group };
}

export function buildEventTypeOptions(lang: 'fr' | 'en'): ExplanatoryOption[] {
  const dict = eventTypeExplanations[lang];
  return Object.entries(dict)
    .map(([id, meta]) => metaToOption(id, meta))
    .sort((a, b) => a.label.localeCompare(b.label, lang));
}

export function buildDirectionOptions(lang: 'fr' | 'en'): ExplanatoryOption[] {
  const dict = directionExplanations[lang];
  return Object.keys(dict).map((id) => metaToOption(id, dict[id]));
}

export function buildClassFilterOptions(
  lang: 'fr' | 'en',
  groupsLabel: string,
  cocoLabel: string,
  extraClasses?: string[],
): ExplanatoryOption[] {
  const groups = classGroupExplanations[lang];
  const coco = cocoClassExplanations[lang];
  const groupOpts = Object.entries(groups).map(([id, meta]) => metaToOption(id, meta, groupsLabel));
  const cocoOpts = Object.entries(coco).map(([id, meta]) => metaToOption(id, meta, cocoLabel));
  const seen = new Set<string>([...groupOpts, ...cocoOpts].map((o) => o.value));
  const registryOpts: ExplanatoryOption[] = [];
  for (const cls of extraClasses ?? []) {
    if (!cls || seen.has(cls)) continue;
    seen.add(cls);
    registryOpts.push({
      value: cls,
      label: cls,
      technicalId: cls,
      technology: lang === 'en' ? 'Registry class' : 'Classe registre',
      howItWorks: lang === 'en' ? 'From ai-models.json / stack registry.' : 'Issue de ai-models.json / registre stack.',
      stepUtility: lang === 'en' ? 'Filter on this detection class.' : 'Filtre sur cette classe de détection.',
    });
  }
  return [...groupOpts, ...cocoOpts, ...registryOpts];
}

export function buildZoneOptions(
  zones: Array<{ id: string; name: string }>,
  lang: 'fr' | 'en',
): ExplanatoryOption[] {
  const isEn = lang === 'en';
  return zones.map((z) => ({
    value: z.name,
    label: z.name,
    technicalId: z.id,
    technology: isEn ? 'Spatial zone (polygon)' : 'Zone spatiale (polygone)',
    howItWorks: isEn
      ? 'Area drawn on the camera in the spatial editor.'
      : 'Zone dessinée sur la caméra dans l’éditeur spatial.',
    stepUtility: isEn
      ? 'At the Conditions step: filter events to this zone only.'
      : 'À l’étape Conditions : filtre les événements sur cette zone uniquement.',
  }));
}

export function buildLineOptions(
  lines: Array<{ id: string; name: string }>,
  lang: 'fr' | 'en',
): ExplanatoryOption[] {
  const isEn = lang === 'en';
  return lines.map((l) => ({
    value: l.name,
    label: l.name,
    technicalId: l.id,
    technology: isEn ? 'Counting line' : 'Ligne de comptage',
    howItWorks: isEn
      ? 'Line drawn on the camera for crossing detection.'
      : 'Ligne tracée sur la caméra pour détecter les franchissements.',
    stepUtility: isEn
      ? 'At the Conditions step: trigger when an object crosses this line.'
      : 'À l’étape Conditions : déclenche quand un objet franchit cette ligne.',
  }));
}

export function buildCameraOptions(
  cameras: Array<{ id: string; name: string }>,
  lang: 'fr' | 'en',
): ExplanatoryOption[] {
  const isEn = lang === 'en';
  return cameras.map((c) => ({
    value: c.id,
    label: c.name,
    technicalId: c.id,
    technology: isEn ? 'RTSP video source' : 'Source vidéo RTSP',
    howItWorks: isEn
      ? 'Live stream ingested by the video and AI pipeline.'
      : 'Flux live ingéré par le pipeline vidéo et IA.',
    stepUtility: isEn
      ? 'At step 1: selects which camera this rule monitors.'
      : 'À l’étape 1 : choisit la caméra surveillée par cette règle.',
  }));
}

export function buildSurveillanceListOptions(
  lists: Array<{ id: string; name: string }>,
  lang: 'fr' | 'en',
  kind: 'watchlist' | 'plate_list',
): ExplanatoryOption[] {
  const isEn = lang === 'en';
  const isPlate = kind === 'plate_list';
  return lists.map((item) => ({
    value: item.id,
    label: item.name,
    technicalId: item.id,
    technology: isEn
      ? isPlate ? 'License plate list' : 'Face watchlist'
      : isPlate ? 'Liste de plaques' : 'Liste de surveillance identité',
    howItWorks: isEn
      ? isPlate
        ? 'Registered plates compared against ANPR detections.'
        : 'Registered faces compared against face recognition matches.'
      : isPlate
        ? 'Plaques enregistrées comparées aux détections ANPR.'
        : 'Visages enregistrés comparés aux correspondances reconnaissance faciale.',
    stepUtility: isEn
      ? 'At step 1: triggers when a match is found in this list.'
      : 'À l’étape 1 : déclenche quand une correspondance est trouvée dans cette liste.',
  }));
}

export function buildSchemaEnumOptions(
  options: Array<string | { value: string; label: string }>,
  lang: 'fr' | 'en',
  fieldKey: string,
): ExplanatoryOption[] {
  const isEn = lang === 'en';
  return options.map((opt) => {
    const val = typeof opt === 'string' ? opt : opt.value;
    const lab = typeof opt === 'string' ? opt : opt.label;
    return {
      value: val,
      label: lab,
      technicalId: val,
      technology: isEn ? 'Rule parameter' : 'Paramètre de règle',
      howItWorks: isEn
        ? `Allowed value for field « ${fieldKey} ».`
        : `Valeur autorisée pour le champ « ${fieldKey} ».`,
      stepUtility: isEn
        ? 'At step 1: refines how the rule behaves.'
        : 'À l’étape 1 : affine le comportement de la règle.',
    };
  });
}

export function buildSeverityOptions(
  lang: 'fr' | 'en',
  labels: { low: string; medium: string; high: string; critical: string },
): ExplanatoryOption[] {
  const isEn = lang === 'en';
  const details: Record<string, { how: string; util: string }> = isEn
    ? {
        low: { how: 'Discrete in-app notification.', util: 'For informational events.' },
        medium: { how: 'Visible badge and optional sound.', util: 'Standard operational alerts.' },
        high: { how: 'Prominent red banner in the UI.', util: 'Important situations requiring attention.' },
        critical: { how: 'Continuous sound + push notification.', util: 'Reserve for urgent emergencies only.' },
      }
    : {
        low: { how: 'Notification discrète dans l’application.', util: 'Pour événements informatifs.' },
        medium: { how: 'Badge visible et son optionnel.', util: 'Alertes opérationnelles standard.' },
        high: { how: 'Bandeau rouge proéminent dans l’interface.', util: 'Situations importantes nécessitant attention.' },
        critical: { how: 'Alerte sonore continue + notification push.', util: 'À réserver aux urgences critiques.' },
      };
  return (['low', 'medium', 'high', 'critical'] as const).map((id) => ({
    value: id,
    label: labels[id],
    technicalId: id,
    technology: isEn ? 'Alert priority' : 'Priorité d’alerte',
    howItWorks: details[id].how,
    stepUtility: details[id].util,
  }));
}

export function buildWebhookPresetOptions(
  presets: ReadonlyArray<{ id: string; label: string; hint?: string }>,
  lang: 'fr' | 'en',
): ExplanatoryOption[] {
  const isEn = lang === 'en';
  return presets.map((p) => ({
    value: p.id,
    label: p.label,
    technicalId: p.id || 'custom',
    technology: isEn ? 'Webhook integration' : 'Intégration webhook',
    howItWorks: p.hint ?? (isEn ? 'Sends alert payload to an external URL.' : 'Envoie la charge d’alerte vers une URL externe.'),
    stepUtility: isEn
      ? 'At the Notifications step: routes alerts to automation tools.'
      : 'À l’étape Notifications : achemine les alertes vers des outils d’automatisation.',
  }));
}

const FIELD_HINTS: Record<'fr' | 'en', Record<string, Omit<ExplanatoryOptionMeta, 'label'>>> = {
  fr: {
    event_type: { technicalId: 'event_type', technology: 'Pipeline IA', howItWorks: 'Type d’événement émis par le moteur d’analyse.', stepUtility: 'Champ principal pour filtrer le déclenchement.' },
    zone_id: { technicalId: 'zone_id', technology: 'Éditeur spatial', howItWorks: 'Identifiant de la zone dessinée sur la caméra.', stepUtility: 'Limite la condition à une zone géographique.' },
    line_id: { technicalId: 'line_id', technology: 'Ligne de comptage', howItWorks: 'Ligne tracée pour détecter les franchissements.', stepUtility: 'Compte ou filtre les passages à un endroit précis.' },
    duration_seconds: { technicalId: 'duration_seconds', technology: 'Suivi temporel', howItWorks: 'Durée en secondes mesurée sur la piste.', stepUtility: 'Détecte présence prolongée ou dépassement de seuil.' },
    speed_kmh: { technicalId: 'speed_kmh', technology: 'Estimation vitesse', howItWorks: 'Vitesse calculée à partir du déplacement.', stepUtility: 'Filtre les véhicules trop rapides ou lents.' },
    class_filter: { technicalId: 'class_filter', technology: 'YOLO — groupes', howItWorks: 'Filtre par catégorie d’objet (personne, véhicule…).', stepUtility: 'Affine la condition sur un type d’objet.' },
    class_name: { technicalId: 'class_name', technology: 'YOLO — classe COCO', howItWorks: 'Classe de détection précise (person, car…).', stepUtility: 'Filtre fin sur une classe COCO exacte.' },
    direction: { technicalId: 'direction', technology: 'Vecteur de déplacement', howItWorks: 'Sens du franchissement ou du déplacement.', stepUtility: 'Distingue entrées, sorties ou sens gauche/droite.' },
    confidence: { technicalId: 'confidence', technology: 'Score YOLO', howItWorks: 'Niveau de confiance de la détection (0–1).', stepUtility: 'Élimine les détections peu fiables.' },
  },
  en: {
    event_type: { technicalId: 'event_type', technology: 'AI pipeline', howItWorks: 'Event type emitted by the analysis engine.', stepUtility: 'Primary field to filter triggering.' },
    zone_id: { technicalId: 'zone_id', technology: 'Spatial editor', howItWorks: 'Zone ID drawn on the camera.', stepUtility: 'Limits the condition to a geographic zone.' },
    line_id: { technicalId: 'line_id', technology: 'Counting line', howItWorks: 'Line drawn for crossing detection.', stepUtility: 'Counts or filters crossings at a specific point.' },
    duration_seconds: { technicalId: 'duration_seconds', technology: 'Temporal tracking', howItWorks: 'Duration in seconds measured on the track.', stepUtility: 'Detects prolonged presence or threshold exceedance.' },
    speed_kmh: { technicalId: 'speed_kmh', technology: 'Speed estimation', howItWorks: 'Speed calculated from movement.', stepUtility: 'Filters vehicles that are too fast or slow.' },
    class_filter: { technicalId: 'class_filter', technology: 'YOLO — groups', howItWorks: 'Filter by object category (person, vehicle…).', stepUtility: 'Refines the condition on an object type.' },
    class_name: { technicalId: 'class_name', technology: 'YOLO — COCO class', howItWorks: 'Precise detection class (person, car…).', stepUtility: 'Fine filter on an exact COCO class.' },
    direction: { technicalId: 'direction', technology: 'Movement vector', howItWorks: 'Crossing or movement direction.', stepUtility: 'Distinguishes in, out, or left/right.' },
    confidence: { technicalId: 'confidence', technology: 'YOLO score', howItWorks: 'Detection confidence level (0–1).', stepUtility: 'Eliminates unreliable detections.' },
  },
};

const OP_HINTS: Record<'fr' | 'en', Record<string, Omit<ExplanatoryOptionMeta, 'label'>>> = {
  fr: {
    eq: { technicalId: 'eq', technology: 'Comparaison', howItWorks: 'La valeur doit être exactement égale.', stepUtility: 'Condition d’égalité stricte.' },
    neq: { technicalId: 'neq', technology: 'Comparaison', howItWorks: 'La valeur doit être différente.', stepUtility: 'Exclut une valeur précise.' },
    gt: { technicalId: 'gt', technology: 'Comparaison numérique', howItWorks: 'Strictement supérieur au seuil.', stepUtility: 'Seuil minimum dépassé.' },
    gte: { technicalId: 'gte', technology: 'Comparaison numérique', howItWorks: 'Supérieur ou égal au seuil.', stepUtility: 'Seuil minimum inclus.' },
    lt: { technicalId: 'lt', technology: 'Comparaison numérique', howItWorks: 'Strictement inférieur au seuil.', stepUtility: 'Seuil maximum non dépassé.' },
    lte: { technicalId: 'lte', technology: 'Comparaison numérique', howItWorks: 'Inférieur ou égal au seuil.', stepUtility: 'Seuil maximum inclus.' },
    in_zone: { technicalId: 'in_zone', technology: 'Géométrie spatiale', howItWorks: 'L’objet est à l’intérieur de la zone.', stepUtility: 'Opérateur spatial pour zones.' },
    cross_line: { technicalId: 'cross_line', technology: 'Franchissement', howItWorks: 'L’objet a franchi la ligne.', stepUtility: 'Opérateur pour lignes de comptage.' },
    matches_class: { technicalId: 'matches_class', technology: 'Filtre classe YOLO', howItWorks: 'La classe détectée correspond au filtre.', stepUtility: 'Opérateur pour classes d’objets.' },
  },
  en: {
    eq: { technicalId: 'eq', technology: 'Comparison', howItWorks: 'Value must be exactly equal.', stepUtility: 'Strict equality condition.' },
    neq: { technicalId: 'neq', technology: 'Comparison', howItWorks: 'Value must be different.', stepUtility: 'Excludes a specific value.' },
    gt: { technicalId: 'gt', technology: 'Numeric comparison', howItWorks: 'Strictly greater than threshold.', stepUtility: 'Minimum threshold exceeded.' },
    gte: { technicalId: 'gte', technology: 'Numeric comparison', howItWorks: 'Greater than or equal to threshold.', stepUtility: 'Minimum threshold included.' },
    lt: { technicalId: 'lt', technology: 'Numeric comparison', howItWorks: 'Strictly less than threshold.', stepUtility: 'Maximum threshold not exceeded.' },
    lte: { technicalId: 'lte', technology: 'Numeric comparison', howItWorks: 'Less than or equal to threshold.', stepUtility: 'Maximum threshold included.' },
    in_zone: { technicalId: 'in_zone', technology: 'Spatial geometry', howItWorks: 'Object is inside the zone.', stepUtility: 'Spatial operator for zones.' },
    cross_line: { technicalId: 'cross_line', technology: 'Crossing', howItWorks: 'Object has crossed the line.', stepUtility: 'Operator for counting lines.' },
    matches_class: { technicalId: 'matches_class', technology: 'YOLO class filter', howItWorks: 'Detected class matches the filter.', stepUtility: 'Operator for object classes.' },
  },
};

export function buildConditionFieldOptions(
  lang: 'fr' | 'en',
  labelFor: (field: string, fallback: string) => string,
): ExplanatoryOption[] {
  const hints = FIELD_HINTS[lang];
  const fields = [
    { value: 'event_type', label: 'Type événement' },
    { value: 'zone_id', label: 'Zone' },
    { value: 'line_id', label: 'Ligne' },
    { value: 'duration_seconds', label: 'Durée (s)' },
    { value: 'speed_kmh', label: 'Vitesse (km/h)' },
    { value: 'class_filter', label: 'Classe objet' },
    { value: 'class_name', label: 'Classe détectée (COCO)' },
    { value: 'direction', label: 'Direction' },
    { value: 'confidence', label: 'Confiance' },
  ];
  return fields.map((f) => {
    const hint = hints[f.value] ?? hints.event_type;
    return metaToOption(f.value, { label: labelFor(f.value, f.label), ...hint });
  });
}

export function buildConditionOpOptions(
  ops: Array<{ value: string; label: string }>,
  lang: 'fr' | 'en',
): ExplanatoryOption[] {
  const hints = OP_HINTS[lang];
  return ops.map((o) => {
    const hint = hints[o.value] ?? hints.eq;
    return metaToOption(o.value, { label: o.label, ...hint });
  });
}

export function buildGroupOpOptions(
  lang: 'fr' | 'en',
  labels: { and: string; or: string; sequence: string; ruleSetOr?: string; ruleSet?: string },
): ExplanatoryOption[] {
  const isEn = lang === 'en';
  const base = [
    {
      value: 'AND',
      label: labels.and,
      technicalId: 'AND',
      technology: isEn ? 'Boolean logic' : 'Logique booléenne',
      howItWorks: isEn ? 'All child conditions must be true.' : 'Toutes les conditions enfants doivent être vraies.',
      stepUtility: isEn ? 'Combine conditions with AND.' : 'Combine les conditions avec ET.',
    },
    {
      value: 'OR',
      label: labels.or,
      technicalId: 'OR',
      technology: isEn ? 'Boolean logic' : 'Logique booléenne',
      howItWorks: isEn ? 'At least one child condition must be true.' : 'Au moins une condition enfant doit être vraie.',
      stepUtility: isEn ? 'Combine conditions with OR.' : 'Combine les conditions avec OU.',
    },
    {
      value: 'SEQUENCE',
      label: labels.sequence,
      technicalId: 'SEQUENCE',
      technology: isEn ? 'Temporal sequence' : 'Séquence temporelle',
      howItWorks: isEn ? 'Conditions must occur in order over time.' : 'Les conditions doivent se produire dans l’ordre.',
      stepUtility: isEn ? 'For multi-step scenarios.' : 'Pour scénarios multi-étapes.',
    },
    {
      value: 'RULE_SET_OR',
      label: labels.ruleSetOr ?? (isEn ? 'Event set (OR)' : 'Ensemble événements (OU)'),
      technicalId: 'RULE_SET_OR',
      technology: isEn ? 'Observation counting' : 'Comptage observation',
      howItWorks: isEn ? 'Increment when any child event type matches.' : 'Incrémente dès qu\'un type d\'événement enfant correspond.',
      stepUtility: isEn ? 'For neutral multi-event counting.' : 'Pour comptage multi-événements neutre.',
    },
    {
      value: 'RULE_SET',
      label: labels.ruleSet ?? (isEn ? 'Event set (N-of-M)' : 'Ensemble événements (N-sur-M)'),
      technicalId: 'RULE_SET',
      technology: isEn ? 'Observation counting' : 'Comptage observation',
      howItWorks: isEn ? 'Increment when N distinct event types match within a window.' : 'Incrémente quand N types distincts correspondent dans une fenêtre.',
      stepUtility: isEn ? 'For combined observation patterns.' : 'Pour patterns d\'observation combinés.',
    },
  ];
  return base;
}

export function eventTypeLabel(value: string, lang: 'fr' | 'en'): string {
  const meta = eventTypesRaw[value];
  if (!meta) return value;
  return lang === 'en' ? (meta.label_en ?? meta.label_fr ?? value) : (meta.label_fr ?? value);
}

export function templatePrimaryEventType(definition: { condition?: { field?: string; value?: unknown } } | undefined): string {
  const cond = definition?.condition;
  if (cond?.field === 'event_type' && cond.value != null) return String(cond.value);
  return '';
}
