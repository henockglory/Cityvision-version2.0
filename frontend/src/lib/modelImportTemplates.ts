import type { ExplanatoryOption } from '@/components/ui/ExplanatorySelect';
import type { OrgModelRow } from '@/api/client';

/** Base structure ids; dynamic org entries use `org:{modelId}`. */
export type ModelStructureId = 'custom' | 'classification' | 'detection' | `org:${string}`;

export interface ModelImportStructure {
  id: ModelStructureId;
  label_fr: string;
  label_en: string;
  description_fr: string;
  description_en: string;
  task: 'classification' | 'detection';
  applies_to: 'zone' | 'line' | 'both';
  input_source: 'crop_vehicle' | 'crop_zone' | 'full_frame';
  input_size: number;
  classes: string[];
  positive_classes: string[];
  capability: 'real' | 'beta';
  behavior?: string;
  event_type?: string;
  /** When set, pre-fill identity fields from an existing org model. */
  fromOrgModel?: OrgModelRow;
}

const BASE_STRUCTURES: ModelImportStructure[] = [
  {
    id: 'custom',
    label_fr: 'Configuration libre',
    label_en: 'Free configuration',
    description_fr: 'Vous définissez identifiant, classes, événement et portée pour votre modèle ONNX.',
    description_en: 'You define id, classes, event type and scope for your ONNX model.',
    task: 'classification',
    applies_to: 'zone',
    input_source: 'crop_vehicle',
    input_size: 224,
    classes: ['negative', 'positive'],
    positive_classes: ['positive'],
    capability: 'beta',
  },
  {
    id: 'classification',
    label_fr: 'Classification (zone ou habitacle)',
    label_en: 'Classification (zone or cabin crop)',
    description_fr: 'Pré-remplit une structure classification — vous nommez le modèle et l\'événement émis.',
    description_en: 'Pre-fills a classification structure — you name the model and emitted event.',
    task: 'classification',
    applies_to: 'zone',
    input_source: 'crop_vehicle',
    input_size: 224,
    classes: ['negative', 'positive'],
    positive_classes: ['positive'],
    capability: 'beta',
  },
  {
    id: 'detection',
    label_fr: 'Détection (zone ou habitacle)',
    label_en: 'Detection (zone or cabin crop)',
    description_fr: 'Pré-remplit une structure détection — classes et événement à personnaliser.',
    description_en: 'Pre-fills a detection structure — customize classes and event type.',
    task: 'detection',
    applies_to: 'zone',
    input_source: 'crop_vehicle',
    input_size: 640,
    classes: ['class_a', 'class_b'],
    positive_classes: ['class_b'],
    capability: 'beta',
  },
];

export function orgModelToStructure(m: OrgModelRow): ModelImportStructure {
  return {
    id: `org:${m.id}`,
    label_fr: `Réutiliser · ${m.label_fr}`,
    label_en: `Reuse · ${m.label_en ?? m.label_fr}`,
    description_fr: m.human_description_fr ?? `Reprend les métadonnées du modèle « ${m.label_fr} » (nouveau fichier .onnx).`,
    description_en: `Reuses metadata from « ${m.label_en ?? m.label_fr} » (new .onnx file).`,
    task: (m.task === 'detection' ? 'detection' : 'classification'),
    applies_to: (m.applies_to as ModelImportStructure['applies_to']) ?? 'zone',
    input_source: (m.input_source as ModelImportStructure['input_source']) ?? 'crop_vehicle',
    input_size: m.input_size ?? (m.task === 'detection' ? 640 : 224),
    classes: m.classes?.length ? m.classes : ['negative', 'positive'],
    positive_classes: m.positive_classes?.length ? m.positive_classes : ['positive'],
    capability: (m.capability === 'real' ? 'real' : 'beta'),
    behavior: m.behavior,
    event_type: m.event_type,
    fromOrgModel: m,
  };
}

export function resolveModelImportStructure(
  id: string,
  orgModels: OrgModelRow[] = [],
): ModelImportStructure | undefined {
  const base = BASE_STRUCTURES.find((x) => x.id === id);
  if (base) return base;
  if (id.startsWith('org:')) {
    const mid = id.slice(4);
    const m = orgModels.find((x) => x.id === mid);
    return m ? orgModelToStructure(m) : undefined;
  }
  return undefined;
}

export function buildModelImportStructureOptions(
  lang: 'fr' | 'en',
  orgModels: OrgModelRow[] = [],
): ExplanatoryOption[] {
  const isEn = lang === 'en';
  const opts: ExplanatoryOption[] = BASE_STRUCTURES.map((tpl) => ({
    value: tpl.id,
    label: isEn ? tpl.label_en : tpl.label_fr,
    technicalId: tpl.task,
    technology: isEn ? `Scope: ${tpl.applies_to}` : `Portée : ${tpl.applies_to}`,
    howItWorks: isEn ? tpl.description_en : tpl.description_fr,
    stepUtility: isEn
      ? 'Pre-fills technical fields — identity stays yours to define.'
      : 'Pré-remplit les champs techniques — l\'identité reste à votre charge.',
    group: isEn ? 'Import structure' : 'Structure d\'import',
  }));

  for (const m of orgModels) {
    const tpl = orgModelToStructure(m);
    opts.push({
      value: tpl.id,
      label: isEn ? tpl.label_en : tpl.label_fr,
      technicalId: m.id,
      technology: isEn ? `Event: ${m.event_type}` : `Événement : ${m.event_type}`,
      howItWorks: isEn ? tpl.description_en : tpl.description_fr,
      stepUtility: isEn
        ? 'Copy metadata from an existing org model for a new ONNX file.'
        : 'Reprend les métadonnées d\'un modèle déjà importé pour un nouveau fichier ONNX.',
      group: isEn ? 'Existing org models' : 'Modèles déjà importés',
    });
  }

  return opts;
}

/** @deprecated use resolveModelImportStructure */
export const MODEL_IMPORT_TEMPLATES = BASE_STRUCTURES;

export type ModelTemplateId = ModelStructureId;

export function slugifyModelId(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .replace(/^([^a-z])/, 'm_$1')
    .slice(0, 49);
}

export function slugifyEventType(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 64);
}
