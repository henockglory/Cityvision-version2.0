export type ConditionNode = {
  op?: string;
  field?: string;
  value?: unknown;
  children?: ConditionNode[];
};

export function cloneCondition(node: ConditionNode | undefined): ConditionNode | undefined {
  if (!node) return undefined;
  return JSON.parse(JSON.stringify(node)) as ConditionNode;
}

export function isGroupNode(node: ConditionNode): boolean {
  const op = String(node.op ?? '').toUpperCase();
  return op === 'AND' || op === 'OR' || op === 'SEQUENCE';
}

export function createLeaf(field = 'event_type', op = 'eq', value = ''): ConditionNode {
  return { field, op, value };
}

export function createGroup(op: 'AND' | 'OR' = 'AND', children: ConditionNode[] = []): ConditionNode {
  return { op, children };
}

export function validateConditionTree(node: ConditionNode | undefined): string | null {
  if (!node) return 'Condition manquante';
  if (isGroupNode(node)) {
    if (!node.children?.length) return 'Groupe vide — ajoutez une condition ou supprimez le groupe';
    for (const c of node.children) {
      const err = validateConditionTree(c);
      if (err) return err;
    }
    return null;
  }
  if (!node.field || !node.op) return 'Condition incomplète (champ ou opérateur manquant)';
  return null;
}

export const CONDITION_FIELDS = [
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

export const CONDITION_OPS = [
  { value: 'eq', label: '=' },
  { value: 'neq', label: '≠' },
  { value: 'gt', label: '>' },
  { value: 'gte', label: '≥' },
  { value: 'lt', label: '<' },
  { value: 'lte', label: '≤' },
  { value: 'in_zone', label: 'Dans zone' },
  { value: 'cross_line', label: 'Franchit ligne' },
  { value: 'matches_class', label: 'Correspond à la classe' },
];

export const OPS_FOR_FIELD: Record<string, string[]> = {
  event_type: ['eq', 'neq'],
  zone_id: ['eq', 'in_zone'],
  line_id: ['eq', 'cross_line'],
  duration_seconds: ['eq', 'neq', 'gt', 'gte', 'lt', 'lte'],
  speed_kmh: ['eq', 'neq', 'gt', 'gte', 'lt', 'lte'],
  class_filter: ['eq', 'matches_class'],
  class_name: ['eq', 'matches_class'],
  direction: ['eq', 'neq'],
  confidence: ['eq', 'neq', 'gt', 'gte', 'lt', 'lte'],
};

export function opsForField(field: string): typeof CONDITION_OPS {
  const allowed = OPS_FOR_FIELD[field];
  if (!allowed) return CONDITION_OPS;
  return CONDITION_OPS.filter((o) => allowed.includes(o.value));
}
