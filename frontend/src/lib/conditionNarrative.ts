import type { TFunction } from 'i18next';
import type { ConditionNode } from '@/lib/conditionTree';
import { isGroupNode } from '@/lib/conditionTree';

export type NarrativeContext = {
  zoneName?: string;
  lineName?: string;
  classFilter?: string;
  cameraName?: string;
};

function resolveValue(
  field: string,
  value: unknown,
  ctx: NarrativeContext,
  t: TFunction,
): string {
  if (field === 'zone_id' && ctx.zoneName) return ctx.zoneName;
  if (field === 'line_id' && ctx.lineName) return ctx.lineName;
  if ((field === 'class_name' || field === 'class_filter') && ctx.classFilter) {
    return t(`rules.narrative.classes.${ctx.classFilter}`, String(value ?? ctx.classFilter));
  }
  if (field === 'event_type') {
    const key = String(value ?? '');
    return t(`rules.narrative.events.${key}`, key);
  }
  if (field === 'class_name' || field === 'class_filter') {
    return t(`rules.narrative.classes.${String(value)}`, String(value ?? ''));
  }
  return String(value ?? '');
}

function leafSentence(node: ConditionNode, ctx: NarrativeContext, t: TFunction): string {
  const field = node.field ?? '';
  const op = String(node.op ?? 'eq').toLowerCase();
  const val = resolveValue(field, node.value, ctx, t);

  if (field === 'event_type' && op === 'eq') {
    return t('rules.narrative.leaf.eventType', { event: val });
  }
  if (field === 'zone_id' || op === 'in_zone') {
    return t('rules.narrative.leaf.inZone', { zone: val });
  }
  if (field === 'line_id' || op === 'cross_line') {
    return t('rules.narrative.leaf.crossLine', { line: val });
  }
  if (field === 'duration_seconds' && (op === 'gt' || op === 'gte')) {
    return t('rules.narrative.leaf.durationAtLeast', { seconds: val });
  }
  if (field === 'speed_kmh' && (op === 'gt' || op === 'gte')) {
    return t('rules.narrative.leaf.speedAbove', { speed: val });
  }
  if (field === 'class_name' && op === 'matches_class') {
    return t('rules.narrative.leaf.objectClass', { cls: val });
  }
  if (field === 'confidence' && (op === 'gt' || op === 'gte')) {
    return t('rules.narrative.leaf.confidenceAtLeast', { pct: val });
  }

  const fieldLabel = t(`rules.narrative.fields.${field}`, field);
  const opLabel = t(`rules.narrative.ops.${op}`, op);
  return t('rules.narrative.leaf.generic', { field: fieldLabel, op: opLabel, value: val });
}

function groupIntro(node: ConditionNode, t: TFunction): string {
  const op = String(node.op ?? 'AND').toUpperCase();
  if (op === 'OU' || op === 'OR') return t('rules.narrative.group.orIntro');
  if (op === 'SEQUENCE') return t('rules.narrative.group.sequenceIntro');
  return t('rules.narrative.group.andIntro');
}

export function narrateConditionTree(
  node: ConditionNode | undefined,
  t: TFunction,
  ctx: NarrativeContext = {},
  depth = 0,
): string[] {
  if (!node) return [];
  if (isGroupNode(node)) {
    const lines: string[] = [];
    if (depth === 0) lines.push(groupIntro(node, t));
    else lines.push(`${'  '.repeat(depth - 1)}${groupIntro(node, t)}`);
    for (const child of node.children ?? []) {
      lines.push(...narrateConditionTree(child, t, ctx, depth + 1));
    }
    return lines;
  }
  const prefix = depth > 0 ? `${'  '.repeat(depth)}• ` : '• ';
  return [`${prefix}${leafSentence(node, ctx, t)}`];
}

export function narrateConditionSummary(
  node: ConditionNode | undefined,
  t: TFunction,
  ctx: NarrativeContext = {},
): string {
  const lines = narrateConditionTree(node, t, ctx);
  if (lines.length === 0) return t('rules.narrative.empty');
  if (lines.length === 1) return lines[0].replace(/^•\s*/, '');
  return lines.join('\n');
}

export function technicalLeafLine(node: ConditionNode): string {
  if (isGroupNode(node)) {
    const op = String(node.op ?? 'AND').toUpperCase();
    return op;
  }
  const field = node.field ?? '?';
  const op = String(node.op ?? 'eq');
  const val = node.value != null ? JSON.stringify(node.value) : '""';
  return `${field} ${op} ${val}`;
}
