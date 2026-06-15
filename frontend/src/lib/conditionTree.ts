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
  return op === 'AND' || op === 'OR';
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
