import type { ConditionNode } from '@/lib/conditionTree';
import { isGroupNode } from '@/lib/conditionTree';

const VEHICLE_CLASSES = new Set([
  'vehicle',
  'car',
  'truck',
  'bus',
  'motorcycle',
  'bicycle',
  'train',
  'boat',
  'airplane',
]);

function fieldValue(payload: Record<string, unknown>, field: string): unknown {
  if (!field) return undefined;
  if (!field.includes('.')) return payload[field];
  let cur: unknown = payload;
  for (const part of field.split('.')) {
    if (cur == null || typeof cur !== 'object') return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return cur;
}

function toFloat(v: unknown): number | null {
  if (typeof v === 'number' && !Number.isNaN(v)) return v;
  if (typeof v === 'string' && v !== '' && !Number.isNaN(Number(v))) return Number(v);
  return null;
}

function matchesClass(actual: string, expected: string): boolean {
  const a = actual.toLowerCase();
  const e = expected.toLowerCase().trim();
  // Mirror rules-engine: empty / any never deserts when class is omitted.
  if (e === '' || e === 'any') return true;
  if (e === 'vehicle') return VEHICLE_CLASSES.has(a);
  if (e === 'person') return a === 'person';
  return a === e;
}

function resolveDetectedClass(payload: Record<string, unknown>, field: string): unknown {
  const f = String(field || '').trim();
  if (f && f.toLowerCase() !== 'class_filter') {
    const v = fieldValue(payload, f);
    if (v !== undefined && v !== null && String(v).trim() !== '') return v;
  }
  const meta =
    payload.metadata && typeof payload.metadata === 'object'
      ? (payload.metadata as Record<string, unknown>)
      : {};
  for (const candidate of [
    payload.class_name,
    payload.detected_class,
    payload.label,
    payload.frigate_label,
    meta.frigate_label,
    meta.detected_class,
    meta.label,
  ]) {
    if (candidate !== undefined && candidate !== null && String(candidate).trim() !== '') {
      return candidate;
    }
  }
  return undefined;
}

/** Client-side mirror of rules-engine evalCondition (single-event evaluation). */
export function evaluateConditionNode(
  node: ConditionNode | undefined,
  payload: Record<string, unknown>,
): boolean {
  if (!node) return false;
  const op = String(node.op ?? '').toUpperCase();

  if (op === 'ET' || op === 'AND') {
    if (!node.children?.length) return false;
    return node.children.every((c) => evaluateConditionNode(c, payload));
  }
  if (op === 'OU' || op === 'OR') {
    if (!node.children?.length) return false;
    return node.children.some((c) => evaluateConditionNode(c, payload));
  }
  if (op === 'NON' || op === 'NOT') {
    if (node.children?.length === 1) return !evaluateConditionNode(node.children[0], payload);
    return false;
  }

  if (op === 'SEQUENCE') {
    if (!node.children?.length) return false;
    return node.children.every((c) => evaluateConditionNode(c, payload));
  }

  const field = node.field ?? '';
  const leafOp = op.toLowerCase();

  if (leafOp === 'matches_class') {
    const expected = String(node.value ?? '').trim().toLowerCase();
    if (expected === '' || expected === 'any') return true;
    const raw = resolveDetectedClass(payload, field);
    if (raw === undefined) return false;
    return matchesClass(String(raw), expected);
  }

  const raw = fieldValue(payload, field);
  if (raw === undefined) return false;

  if (leafOp === 'eq') return String(raw) === String(node.value ?? '');
  if (leafOp === 'neq') return String(raw) !== String(node.value ?? '');
  if (leafOp === 'gt') {
    const v = toFloat(raw);
    const e = toFloat(node.value);
    return v != null && e != null && v > e;
  }
  if (leafOp === 'gte') {
    const v = toFloat(raw);
    const e = toFloat(node.value);
    return v != null && e != null && v >= e;
  }
  if (leafOp === 'lt') {
    const v = toFloat(raw);
    const e = toFloat(node.value);
    return v != null && e != null && v < e;
  }
  if (leafOp === 'lte') {
    const v = toFloat(raw);
    const e = toFloat(node.value);
    return v != null && e != null && v <= e;
  }
  if (leafOp === 'in_zone' || leafOp === 'cross_line') {
    return String(raw) === String(node.value ?? '');
  }
  if (leafOp === 'contains') {
    return String(raw).includes(String(node.value ?? ''));
  }
  return false;
}

export function isLogicGroup(node: ConditionNode): boolean {
  return isGroupNode(node);
}
