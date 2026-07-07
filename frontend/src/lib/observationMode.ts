export type ObservationKind = 'line_cross' | 'event' | 'rule_set_or' | 'rule_set_n';

export const OBSERVATION_TEMPLATE_IDS = new Set([
  'tpl-line-cross',
  'tpl-line-cross-bidir',
  'tpl-speeding-premium',
  'tpl-observation-rule-set-or',
  'tpl-observation-rule-set-n',
]);

export function isObservationTemplate(templateId?: string | null): boolean {
  return Boolean(templateId && OBSERVATION_TEMPLATE_IDS.has(templateId));
}

export function defaultObservationKind(templateId?: string | null): ObservationKind {
  if (templateId === 'tpl-line-cross' || templateId === 'tpl-line-cross-bidir') return 'line_cross';
  if (templateId === 'tpl-observation-rule-set-or') return 'rule_set_or';
  if (templateId === 'tpl-observation-rule-set-n') return 'rule_set_n';
  return 'event';
}
