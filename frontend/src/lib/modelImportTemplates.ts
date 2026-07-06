export type ModelTemplateId = 'custom' | 'phone_use' | 'seatbelt' | 'classification' | 'detection';

export interface ModelImportTemplate {
  id: ModelTemplateId;
  label_fr: string;
  label_en: string;
  description_fr: string;
  description_en: string;
  task: 'classification' | 'detection';
  applies_to: 'zone' | 'line' | 'both';
  input_source: 'crop_vehicle' | 'crop_zone' | 'full_frame';
  input_size: number;
  behavior?: string;
  event_type?: string;
  classes: string[];
  positive_classes: string[];
  capability: 'real' | 'beta';
}

export const MODEL_IMPORT_TEMPLATES: ModelImportTemplate[] = [
  {
    id: 'custom',
    label_fr: 'Personnalisé (tous champs)',
    label_en: 'Custom (all fields)',
    description_fr: 'Vous définissez identifiant, classes, événement et portée. Pour un modèle ONNX unique à votre organisation.',
    description_en: 'You define id, classes, event and scope. For an org-specific ONNX model.',
    task: 'classification',
    applies_to: 'zone',
    input_source: 'crop_vehicle',
    input_size: 224,
    classes: ['negative', 'positive'],
    positive_classes: ['positive'],
    capability: 'beta',
  },
  {
    id: 'phone_use',
    label_fr: 'Gabarit · Téléphone au volant',
    label_en: 'Template · Phone while driving',
    description_fr: 'Classification habitacle (comme driver_phone produit). Le fichier ONNX doit correspondre à ce gabarit.',
    description_en: 'Cabin classification (like product driver_phone). ONNX file must match this template.',
    task: 'classification',
    applies_to: 'zone',
    input_source: 'crop_vehicle',
    input_size: 224,
    behavior: 'custom:driver_phone',
    event_type: 'phone_use_violation',
    classes: ['c0', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'c8', 'c9'],
    positive_classes: ['c1', 'c2', 'c3', 'c4'],
    capability: 'real',
  },
  {
    id: 'seatbelt',
    label_fr: 'Gabarit · Ceinture non portée',
    label_en: 'Template · Seatbelt violation',
    description_fr: 'Détection YOLO-cls dans l\'habitacle (comme seatbelt produit). Fichier .onnx requis.',
    description_en: 'Cabin detection (like product seatbelt). Requires .onnx file.',
    task: 'detection',
    applies_to: 'zone',
    input_source: 'crop_vehicle',
    input_size: 640,
    behavior: 'custom:seatbelt',
    event_type: 'seatbelt_violation',
    classes: ['Seat_Belt', 'Without_Seat_Belt'],
    positive_classes: ['Without_Seat_Belt'],
    capability: 'real',
  },
  {
    id: 'classification',
    label_fr: 'Classification générique (zone)',
    label_en: 'Generic classification (zone)',
    description_fr: 'Modèle de classes sur crop véhicule ou zone. Événement personnalisé à définir.',
    description_en: 'Multi-class model on vehicle/zone crop. Custom event type required.',
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
    label_fr: 'Détection générique (zone)',
    label_en: 'Generic detection (zone)',
    description_fr: 'Détection d\'objets dans le crop. Événement et classes à préciser.',
    description_en: 'Object detection in crop. Event and classes required.',
    task: 'detection',
    applies_to: 'zone',
    input_source: 'crop_vehicle',
    input_size: 640,
    classes: ['class_a', 'class_b'],
    positive_classes: ['class_b'],
    capability: 'beta',
  },
];

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
