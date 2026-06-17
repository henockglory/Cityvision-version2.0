export interface EvidenceImageSpec {
  role: 'scene' | 'subject';
  label?: string;
  crop?: 'full' | 'bbox' | 'bbox_zoom';
  padding_pct?: number;
  zoom?: number;
}

export interface EvidencePolicy {
  enabled: boolean;
  clip_seconds: number;
  images: EvidenceImageSpec[];
  min_confidence?: number;
  draw_bbox?: boolean;
}

export function setEvidenceImageCount(policy: EvidencePolicy, count: number): EvidencePolicy {
  const n = Math.min(3, Math.max(1, count));
  const defaults = DEFAULT_EVIDENCE_POLICY.images;
  const images: EvidenceImageSpec[] = [];
  for (let i = 0; i < n; i++) {
    images.push({ ...(defaults[i] ?? defaults[defaults.length - 1]) });
  }
  return { ...policy, images };
}

export function evidencePolicyChip(policy?: Partial<EvidencePolicy> | null): string {
  const p = normalizeEvidencePolicy(policy);
  if (!p.enabled) return 'preuves off';
  const parts = [`${p.clip_seconds}s`, `${p.images.length} photo${p.images.length > 1 ? 's' : ''}`];
  if (p.draw_bbox) parts.push('cadre');
  return parts.join(' · ');
}

export function normalizeEvidencePolicy(raw?: Partial<EvidencePolicy> | null): EvidencePolicy {
  if (!raw) return { ...DEFAULT_EVIDENCE_POLICY, images: [...DEFAULT_EVIDENCE_POLICY.images] };
  return {
    ...DEFAULT_EVIDENCE_POLICY,
    ...raw,
    images: raw.images?.length ? raw.images : DEFAULT_EVIDENCE_POLICY.images,
  };
}

export const DEFAULT_EVIDENCE_POLICY: EvidencePolicy = {
  enabled: true,
  clip_seconds: 6,
  images: [
    { role: 'scene', label: 'Vue d\'ensemble', crop: 'full' },
    { role: 'subject', label: 'Cible détectée', crop: 'bbox', padding_pct: 10, zoom: 1.0 },
  ],
  min_confidence: 0,
  draw_bbox: true,
};

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
  { id: 'gmail', label: 'Gmail (via e-mail)', hint: 'Utilisez plutôt l\'action e-mail avec SMTP configuré.' },
] as const;
