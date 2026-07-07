export type EvidenceImageRole = 'scene' | 'subject' | 'plate';

export interface EvidenceImageSpec {
  role: EvidenceImageRole;
  label?: string;
  crop?: 'full' | 'bbox' | 'bbox_zoom' | 'plate_rear';
  padding_pct?: number;
  zoom?: number;
}

export const EVIDENCE_IMAGE_ROLE_DEFAULTS: Record<EvidenceImageRole, EvidenceImageSpec> = {
  scene: { role: 'scene', label: 'Vue d\'ensemble', crop: 'full' },
  subject: { role: 'subject', label: 'Cible détectée', crop: 'bbox', padding_pct: 12, zoom: 1.0 },
  plate: { role: 'plate', label: 'Plaque', crop: 'plate_rear', padding_pct: 6, zoom: 1.8 },
};

export interface EvidencePolicy {
  enabled: boolean;
  clip_seconds: number;
  images: EvidenceImageSpec[];
  min_confidence?: number;
  draw_bbox?: boolean;
}

const DEFAULT_IMAGE_ROLE_ORDER: EvidenceImageRole[] = ['scene', 'subject', 'plate'];

export function defaultImageSpecForRole(role: EvidenceImageRole): EvidenceImageSpec {
  const base = EVIDENCE_IMAGE_ROLE_DEFAULTS[role];
  return { ...base };
}

export function setEvidenceImageCount(policy: EvidencePolicy, count: number): EvidencePolicy {
  const n = Math.min(3, Math.max(1, count));
  const images: EvidenceImageSpec[] = [];
  for (let i = 0; i < n; i++) {
    const role = DEFAULT_IMAGE_ROLE_ORDER[i] ?? 'scene';
    images.push(defaultImageSpecForRole(role));
  }
  return { ...policy, images };
}

export function setEvidenceImageRole(
  policy: EvidencePolicy,
  index: number,
  role: EvidenceImageRole,
): EvidencePolicy {
  const images = [...policy.images];
  if (index < 0 || index >= images.length) return policy;
  images[index] = defaultImageSpecForRole(role);
  return { ...policy, images };
}

export function evidencePolicyChip(policy?: Partial<EvidencePolicy> | null): string {
  const p = normalizeEvidencePolicy(policy);
  if (!p.enabled) return 'preuves off';
  const roleLabels: Record<EvidenceImageRole, string> = {
    scene: 'scène',
    subject: 'cible',
    plate: 'plaque',
  };
  const roles = p.images.map((img) => roleLabels[img.role] ?? img.role).join('+');
  const parts = [`${p.clip_seconds}s`, roles || `${p.images.length} photo${p.images.length > 1 ? 's' : ''}`];
  if (p.draw_bbox) parts.push('cadre');
  return parts.join(' · ');
}

export function normalizeEvidencePolicy(raw?: Partial<EvidencePolicy> | null): EvidencePolicy {
  if (!raw) return { ...DEFAULT_EVIDENCE_POLICY, images: [...DEFAULT_EVIDENCE_POLICY.images] };
  if (raw.enabled === false) {
    return {
      enabled: false,
      clip_seconds: raw.clip_seconds ?? 0,
      images: raw.images ?? [],
      min_confidence: raw.min_confidence ?? 0,
      draw_bbox: raw.draw_bbox ?? false,
    };
  }
  return {
    ...DEFAULT_EVIDENCE_POLICY,
    ...raw,
    images: raw.images?.length ? raw.images : DEFAULT_EVIDENCE_POLICY.images,
  };
}

export const DEFAULT_EVIDENCE_POLICY: EvidencePolicy = {
  enabled: true,
  clip_seconds: 6,
  images: DEFAULT_IMAGE_ROLE_ORDER.map((role) => defaultImageSpecForRole(role)),
  min_confidence: 0,
  draw_bbox: true,
};

/** Comptage / franchissement : l'événement line_cross suffit ; pas de clip obligatoire par défaut. */
export const COUNTING_EVIDENCE_POLICY: EvidencePolicy = {
  enabled: false,
  clip_seconds: 0,
  images: [],
  draw_bbox: false,
};

const LINE_COUNTING_TEMPLATES = new Set([
  'tpl-line-cross',
  'tpl-line-cross-bidir',
]);

/** Templates that expose the observation structure menu in rule studio. */
const OBSERVATION_STRUCTURE_TEMPLATES = new Set([
  ...LINE_COUNTING_TEMPLATES,
  'tpl-speeding-premium',
  'tpl-observation-rule-set-or',
  'tpl-observation-rule-set-n',
]);

export function evidencePolicyForTemplate(templateId?: string | null, observationMode?: boolean): EvidencePolicy {
  if (observationMode) {
    return { ...COUNTING_EVIDENCE_POLICY };
  }
  if (templateId && LINE_COUNTING_TEMPLATES.has(templateId)) {
    return { ...COUNTING_EVIDENCE_POLICY };
  }
  return { ...DEFAULT_EVIDENCE_POLICY, images: [...DEFAULT_EVIDENCE_POLICY.images] };
}

export function isCountingRuleTemplate(templateId?: string | null): boolean {
  return Boolean(templateId && OBSERVATION_STRUCTURE_TEMPLATES.has(templateId));
}

export function isObservationEvidenceDefault(templateId?: string | null, observationMode?: boolean): boolean {
  return Boolean(observationMode || (templateId && LINE_COUNTING_TEMPLATES.has(templateId)));
}

/** Persist explicit disabled policy so backend does not fall back to default proof requirements. */
export function evidencePolicyForPersistence(policy: EvidencePolicy): EvidencePolicy {
  if (policy.enabled) return normalizeEvidencePolicy(policy);
  return { enabled: false, clip_seconds: 0, images: [], draw_bbox: false, min_confidence: 0 };
}

export const SPATIAL_TEMPLATES_REQUIRING_CLASS = new Set([
  'tpl-zone-presence',
  'tpl-zone-enter',
  'tpl-zone-exit',
  'tpl-line-cross',
  'tpl-line-cross-bidir',
  'tpl-loitering',
  'tpl-intrusion-zone',
]);

export const WEBHOOK_PRESETS = [
  { id: '', label: 'URL personnalisée', hint: 'Serveur web, API interne, facturation…' },
  { id: 'n8n', label: 'n8n', hint: 'Collez l\'URL du nœud Webhook de votre workflow n8n.' },
  { id: 'make', label: 'Make (Integromat)', hint: 'URL du scénario Make — module Webhooks.' },
  { id: 'zapier', label: 'Zapier', hint: 'URL du Catch Hook Zapier.' },
  { id: 'slack', label: 'Slack', hint: 'URL d\'un Incoming Webhook Slack (message formaté).' },
  { id: 'teams', label: 'Microsoft Teams', hint: 'URL d\'un Incoming Webhook Teams (MessageCard).' },
  { id: 'discord', label: 'Discord', hint: 'URL d\'un webhook de salon Discord (embed).' },
  { id: 'gmail', label: 'Gmail (via e-mail)', hint: 'Utilisez plutôt l\'action e-mail avec SMTP configuré.' },
] as const;
