import catalog from '../../../shared/zone-behaviors.json';

export type Capability = 'real' | 'partial' | 'beta';

export interface BehaviorConfigField {
  key: string;
  type: 'number' | 'class_filter' | 'text' | 'enum';
  label_fr: string;
  label_en: string;
  default?: number | string;
  min?: number;
  max?: number;
  step?: number;
  hint_fr?: string;
  hint_en?: string;
  options?: { value: string; label_fr: string; label_en: string }[];
}

export interface ZoneBehavior {
  id: string;
  group: string;
  label_fr: string;
  label_en: string;
  capability: Capability;
  human_description_fr: string;
  human_description_en: string;
  emits: string[];
  requires: string[];
  config_fields: BehaviorConfigField[];
  /** zone = polygon behaviors; line = crossing-line behaviors */
  applies_to?: 'zone' | 'line';
}

export interface BehaviorGroup {
  id: string;
  label_fr: string;
  label_en: string;
}

export const BEHAVIOR_GROUPS = catalog.groups as BehaviorGroup[];
export const ZONE_BEHAVIORS = catalog.behaviors as ZoneBehavior[];

export function getBehavior(id: string | undefined): ZoneBehavior | undefined {
  return ZONE_BEHAVIORS.find((b) => b.id === (id ?? ''));
}

export function behaviorLabel(id: string | undefined, lang: 'fr' | 'en' = 'fr'): string {
  const b = getBehavior(id);
  if (!b) return id ?? '';
  return lang === 'fr' ? b.label_fr : b.label_en;
}

export function behaviorDescription(id: string | undefined, lang: 'fr' | 'en' = 'fr'): string {
  const b = getBehavior(id);
  if (!b) return '';
  return lang === 'fr' ? b.human_description_fr : b.human_description_en;
}

/** Behaviors grouped by their category, in catalog order, for a grouped selector. */
export function behaviorsByGroup(
  appliesTo?: 'zone' | 'line',
): { group: BehaviorGroup; behaviors: ZoneBehavior[] }[] {
  return BEHAVIOR_GROUPS.map((group) => ({
    group,
    behaviors: ZONE_BEHAVIORS.filter((b) => {
      if (b.group !== group.id) return false;
      if (!appliesTo) return true;
      const scope = b.applies_to ?? 'zone';
      return scope === appliesTo;
    }),
  })).filter((g) => g.behaviors.length > 0);
}
