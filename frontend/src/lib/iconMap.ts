/** Professional icon assets — one distinct SVG per rule template. */
const RULES_BASE = '/icons/rules';
const BASE = '/icons';

export const CATEGORY_ICONS: Record<string, string> = {
  security: `${BASE}/security.svg`,
  spatial: `${BASE}/spatial.svg`,
  time: `${BASE}/time.svg`,
  identity: `${BASE}/identity.svg`,
  traffic: `${BASE}/traffic.svg`,
  behavior: `${BASE}/behavior.svg`,
  composite: `${BASE}/composite.svg`,
  crowd: `${BASE}/crowd.svg`,
};

export function iconForCategory(category?: string): string {
  if (!category) return `${BASE}/rule.svg`;
  return CATEGORY_ICONS[category] ?? `${BASE}/rule.svg`;
}

export function iconForTemplate(templateId?: string, category?: string): string {
  if (templateId?.startsWith('tpl-')) {
    return `${RULES_BASE}/${templateId}.svg`;
  }
  return iconForCategory(category);
}

export function iconForMetric(metric: 'cameras' | 'alerts' | 'events' | 'rules'): string {
  const map = {
    cameras: `${BASE}/camera.svg`,
    alerts: `${BASE}/alert.svg`,
    events: `${BASE}/analytics.svg`,
    rules: `${BASE}/rule.svg`,
  };
  return map[metric];
}
