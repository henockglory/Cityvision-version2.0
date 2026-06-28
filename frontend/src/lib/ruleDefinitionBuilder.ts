import type { RuleCatalogTemplate } from '@/types';

export interface RuleActivationConfig {
  cameraId: string;
  zoneName?: string;
  /** Second zone for multi-zone SEQUENCE templates (zone_name_2). */
  zoneName2?: string;
  lineName?: string;
  durationSeconds?: number;
  speedLimitKmh?: number;
  watchlistId?: string;
  plateListId?: string;
  classFilter?: string;
  direction?: string;
  schedule?: { from: string; to: string; allDay?: boolean };
  actions?: Array<{ type: string; config: Record<string, unknown> }>;
}

export type CondNode = {
  op?: string;
  field?: string;
  value?: unknown;
  children?: CondNode[];
};

function cloneCond(node: CondNode): CondNode {
  return JSON.parse(JSON.stringify(node)) as CondNode;
}

function cloneDefinition(def: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(JSON.stringify(def)) as Record<string, unknown>;
}

function setNodeValue(node: CondNode, value: unknown) {
  node.value = value;
}

function isAndGroup(node: CondNode): boolean {
  const op = String(node.op ?? '').toUpperCase();
  return op === 'AND' || op === 'ET';
}

function hasLeaf(node: CondNode, predicate: (n: CondNode) => boolean): boolean {
  if (predicate(node)) return true;
  return (node.children ?? []).some((c) => hasLeaf(c, predicate));
}

function walkAndPatch(node: CondNode | undefined, cfg: RuleActivationConfig) {
  if (!node) return;
  const op = String(node.op ?? '').toLowerCase();
  const field = String(node.field ?? '').toLowerCase();

  if ((op === 'in_zone' || field === 'zone_id') && cfg.zoneName) {
    setNodeValue(node, cfg.zoneName);
  }
  if ((op === 'cross_line' || field === 'line_id') && cfg.lineName) {
    setNodeValue(node, cfg.lineName);
  }
  if (field === 'duration_seconds' && cfg.durationSeconds != null) {
    setNodeValue(node, cfg.durationSeconds);
  }
  if ((field.includes('speed') || field === 'speed_kmh') && cfg.speedLimitKmh != null) {
    setNodeValue(node, cfg.speedLimitKmh);
  }
  if (
    ((field === 'class_name' && op === 'matches_class') ||
      field === 'class_filter' ||
      field === 'class' ||
      field === 'class_name') &&
    cfg.classFilter
  ) {
    setNodeValue(node, cfg.classFilter);
  }
  if (field === 'direction' && cfg.direction) {
    setNodeValue(node, cfg.direction);
  }

  for (const c of node.children ?? []) walkAndPatch(c, cfg);
}

/** Ajoute zone_id, matches_class, line_id manquants puis applique les bindings. */
export function ensureSpatialConditions(root: CondNode, cfg: RuleActivationConfig): CondNode {
  let andRoot = cloneCond(root);
  if (!isAndGroup(andRoot)) {
    andRoot = { op: 'AND', children: [andRoot] };
  }
  if (!andRoot.children) andRoot.children = [];

  if (cfg.zoneName && !hasLeaf(andRoot, (n) => n.field === 'zone_id')) {
    andRoot.children.push({ op: 'eq', field: 'zone_id', value: cfg.zoneName });
  }
  if (
    cfg.classFilter &&
    !hasLeaf(
      andRoot,
      (n) => n.field === 'class_name' && String(n.op ?? '').toLowerCase() === 'matches_class',
    )
  ) {
    andRoot.children.push({ op: 'matches_class', field: 'class_name', value: cfg.classFilter });
  }
  if (cfg.lineName && !hasLeaf(andRoot, (n) => n.field === 'line_id')) {
    andRoot.children.push({ op: 'eq', field: 'line_id', value: cfg.lineName });
  }

  walkAndPatch(andRoot, cfg);
  return andRoot;
}

/** Injecte la configuration utilisateur dans la définition catalogue avant persistance. */
export function buildConfiguredDefinition(
  tpl: RuleCatalogTemplate,
  cfg: RuleActivationConfig,
  conditionOverride?: CondNode,
  options?: { demo?: boolean },
): Record<string, unknown> {
  const def = cloneDefinition(tpl.definition);
  const baseCond = (conditionOverride ?? def.condition) as CondNode;
  def.condition = ensureSpatialConditions(baseCond, cfg);

  const meta: Record<string, unknown> = {
    template_id: tpl.id,
    camera_id: cfg.cameraId,
  };
  if (cfg.zoneName) meta.zone_name = cfg.zoneName;
  if (cfg.zoneName2) meta.zone_name_2 = cfg.zoneName2;
  if (cfg.lineName) meta.line_name = cfg.lineName;
  if (cfg.durationSeconds != null) meta.duration_seconds = cfg.durationSeconds;
  if (cfg.watchlistId) meta.watchlist_id = cfg.watchlistId;
  if (cfg.plateListId) meta.plate_list_id = cfg.plateListId;
  if (cfg.speedLimitKmh != null) meta.speed_kmh = cfg.speedLimitKmh;
  if (cfg.classFilter) meta.class_filter = cfg.classFilter;
  if (cfg.direction) meta.direction = cfg.direction;
  if (cfg.schedule && !cfg.schedule.allDay) meta.schedule = cfg.schedule;
  if (options?.demo) meta.demo = true;

  const actions = cfg.actions?.length
    ? cfg.actions
    : (def.actions as Array<{ type: string; config: Record<string, unknown> }> | undefined);

  return {
    ...def,
    camera_id: cfg.cameraId,
    bindings: meta,
    actions: actions ?? [{ type: 'alert', config: { severity: tpl.severity ?? 'medium' } }],
  };
}

export function activationConfigFromValues(values: Record<string, unknown>): RuleActivationConfig {
  return {
    cameraId: String(values.camera_id ?? ''),
    zoneName: values.zone_name ? String(values.zone_name) : undefined,
    zoneName2: values.zone_name_2 ? String(values.zone_name_2) : undefined,
    lineName: values.line_name ? String(values.line_name) : undefined,
    durationSeconds: values.duration_seconds != null ? Number(values.duration_seconds) : undefined,
    speedLimitKmh: values.speed_kmh != null ? Number(values.speed_kmh) : undefined,
    watchlistId: values.watchlist_id ? String(values.watchlist_id) : undefined,
    plateListId: values.plate_list_id ? String(values.plate_list_id) : undefined,
    classFilter: values.class_filter ? String(values.class_filter) : undefined,
    direction: values.direction ? String(values.direction) : undefined,
    schedule: values.schedule ? (values.schedule as RuleActivationConfig['schedule']) : undefined,
  };
}
