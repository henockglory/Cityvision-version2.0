import type { Rule } from '@/types';

type CondNode = {
  op?: string;
  field?: string;
  value?: unknown;
  children?: CondNode[];
};

function walkCondition(node: CondNode | undefined, visit: (n: CondNode) => void) {
  if (!node) return;
  visit(node);
  for (const c of node.children ?? []) walkCondition(c, visit);
}

const OP_LABELS: Record<string, string> = {
  ET: 'ET',
  AND: 'ET',
  OU: 'OU',
  OR: 'OU',
  EQ: 'égal à',
  GT: 'supérieur à',
  LT: 'inférieur à',
  IN_ZONE: 'dans la zone',
  CROSS_LINE: 'franchit la ligne',
  CONTAINS: 'contient',
};

/** Human-readable explanation of why a rule would trigger. */
export function explainRule(rule: Rule): string {
  const def = rule.definition ?? {};
  const condition = (def.condition ?? def.conditions) as CondNode | undefined;
  const bindings = (def.bindings ?? {}) as Record<string, unknown>;

  const parts: string[] = [];
  walkCondition(condition, (node) => {
    const op = String(node.op ?? '').toUpperCase();
    if (['ET', 'AND', 'OU', 'OR', 'NON', 'NOT'].includes(op)) return;
    const field = node.field ?? '';
    const label = OP_LABELS[op] ?? op;
    let val = node.value;
    if (field === 'zone_id' && bindings.zone_name) val = bindings.zone_name;
    if (field === 'line_id' && bindings.line_name) val = bindings.line_name;
    if (field === 'duration_seconds' && bindings.duration_seconds) val = bindings.duration_seconds;
    parts.push(`${field} ${label} ${String(val ?? '')}`.trim());
  });

  if (parts.length === 0) {
    return rule.description ?? 'Cette règle surveille les événements configurés sur la caméra sélectionnée.';
  }
  return `Alerte lorsque : ${parts.join(' ; ')}.`;
}

export function conditionNodesFromDefinition(definition: Record<string, unknown>): CondNode[] {
  const condition = (definition.condition ?? definition.conditions) as CondNode | undefined;
  if (!condition) return [];
  const nodes: CondNode[] = [];
  walkCondition(condition, (n) => {
    const op = String(n.op ?? '').toUpperCase();
    if (!['ET', 'AND', 'OU', 'OR', 'NON', 'NOT'].includes(op)) nodes.push(n);
  });
  return nodes;
}
