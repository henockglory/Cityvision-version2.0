import type { Rule } from '@/types';
import type { TFunction } from 'i18next';
import { narrateConditionSummary } from '@/lib/conditionNarrative';
import type { NarrativeContext } from '@/lib/conditionNarrative';

type CondNode = {
  op?: string;
  field?: string;
  value?: unknown;
  children?: CondNode[];
};

/** Human-readable explanation of why a rule would trigger. */
export function explainRule(
  rule: Rule,
  t?: TFunction,
  ctx: NarrativeContext = {},
): string {
  const def = rule.definition ?? {};
  const condition = (def.condition ?? def.conditions) as CondNode | undefined;
  const bindings = (def.bindings ?? {}) as Record<string, unknown>;

  const enrichedCtx: NarrativeContext = {
    ...ctx,
    zoneName: ctx.zoneName ?? (bindings.zone_name as string | undefined),
    lineName: ctx.lineName ?? (bindings.line_name as string | undefined),
    classFilter: ctx.classFilter ?? (bindings.class_filter as string | undefined),
  };

  if (t && condition) {
    return narrateConditionSummary(condition, t, enrichedCtx);
  }

  if (!condition) {
    return rule.description ?? 'Cette règle surveille les événements configurés sur la caméra sélectionnée.';
  }

  const parts: string[] = [];
  const walk = (node: CondNode | undefined) => {
    if (!node) return;
    const op = String(node.op ?? '').toUpperCase();
    if (['ET', 'AND', 'OU', 'OR', 'NON', 'NOT', 'SEQUENCE'].includes(op)) {
      for (const c of node.children ?? []) walk(c);
      return;
    }
    parts.push(`${node.field} ${node.op} ${String(node.value ?? '')}`);
  };
  walk(condition);
  if (parts.length === 0) return rule.description ?? '';
  return `Alerte lorsque : ${parts.join(' ; ')}.`;
}

/** Caméra / zone / ligne liées à une règle (affichage liste). */
export function ruleBindingSummary(
  rule: Rule,
  cameras: { id: string; name: string }[] = [],
): string {
  const def = rule.definition ?? {};
  const bindings = (def.bindings ?? {}) as Record<string, unknown>;
  const camId = String(bindings.camera_id ?? def.camera_id ?? '');
  const cam = cameras.find((c) => c.id === camId);
  const camLabel = cam?.name ?? (camId ? `${camId.slice(0, 8)}…` : '—');
  const parts = [`Caméra : ${camLabel}`];
  const zone = bindings.zone_name as string | undefined;
  const line = bindings.line_name as string | undefined;
  if (zone) parts.push(`Zone : ${zone}`);
  if (line) parts.push(`Ligne : ${line}`);
  return parts.join(' · ');
}

export function conditionNodesFromDefinition(definition: Record<string, unknown>): CondNode[] {
  const condition = (definition.condition ?? definition.conditions) as CondNode | undefined;
  if (!condition) return [];
  const nodes: CondNode[] = [];
  const walk = (node: CondNode | undefined) => {
    if (!node) return;
    const op = String(node.op ?? '').toUpperCase();
    if (['ET', 'AND', 'OU', 'OR', 'NON', 'NOT', 'SEQUENCE'].includes(op)) {
      for (const c of node.children ?? []) walk(c);
      return;
    }
    nodes.push(node);
  };
  walk(condition);
  return nodes;
}
