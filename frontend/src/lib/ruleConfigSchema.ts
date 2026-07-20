import type { ConfigSchemaField, RuleCatalogTemplate, RuleConfigSchema } from '@/types';
import { analyzeRuleBindings, bindingLabel, type BindingKind } from '@/lib/ruleRequirements';

const BINDING_TO_TYPE: Record<BindingKind, ConfigSchemaField['type']> = {
  camera: 'camera',
  zone: 'zone',
  line: 'line',
  duration: 'number',
  watchlist: 'watchlist',
  plate: 'plate_list',
  speed_limit: 'number',
};

function bindingToField(kind: BindingKind, required: boolean, hints: Partial<Record<BindingKind, string>>): ConfigSchemaField {
  const field: ConfigSchemaField = {
    key: kind === 'plate' ? 'plate_list_id' : kind === 'speed_limit' ? 'speed_kmh' : kind === 'duration' ? 'duration_seconds' : `${kind}_id`,
    type: BINDING_TO_TYPE[kind],
    label: bindingLabel(kind),
    required,
    hint: hints[kind],
  };
  if (kind === 'duration') {
    field.min = 1;
    field.max = 86400;
    field.default = 120;
  }
  if (kind === 'speed_limit') {
    field.key = 'speed_kmh';
    field.min = 5;
    field.max = 200;
    field.default = 50;
  }
  if (kind === 'camera') field.key = 'camera_id';
  if (kind === 'zone') field.key = 'zone_name';
  if (kind === 'line') field.key = 'line_name';
  return field;
}

/** Resolve config schema: explicit catalog schema or inferred from rule definition. */
export function resolveConfigSchema(template: RuleCatalogTemplate): RuleConfigSchema {
  if (template.configSchema?.fields?.length) {
    return template.configSchema;
  }

  const spec = analyzeRuleBindings(template);
  const fields: ConfigSchemaField[] = [];

  for (const kind of spec.required) {
    fields.push(bindingToField(kind, true, spec.hints));
  }
  for (const kind of spec.optional) {
    if (!spec.required.includes(kind)) {
      fields.push(bindingToField(kind, false, spec.hints));
    }
  }

  const def = template.definition as { window?: unknown };
  if (def.window) {
    fields.push({
      key: 'window',
      type: 'schedule',
      label: 'Plage horaire',
      required: false,
      hint: 'Heures et jours actifs pour cette règle.',
    });
  }

  return { fields };
}

export function getSchemaDefaults(schema: RuleConfigSchema): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of schema.fields) {
    if (f.default !== undefined) out[f.key] = f.default;
  }
  return out;
}
