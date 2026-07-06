import type { CapabilitiesBehaviorMenuItem } from '@/api/client';
import type { ExplanatoryOption } from '@/components/ui/ExplanatorySelect';
import { getBehavior, type ZoneBehavior } from '@/lib/zoneBehaviors';

const GROUP_LABELS: Record<string, { fr: string; en: string }> = {
  access: { fr: 'Accès & présence', en: 'Access & presence' },
  traffic: { fr: 'Circulation & route', en: 'Traffic & road' },
  driver: { fr: 'Conducteur (habitacle)', en: 'Driver (cabin)' },
  safety: { fr: 'Sécurité & comportement', en: 'Safety & behavior' },
  custom: { fr: 'Modèles personnalisés', en: 'Custom models' },
};

function appliesToMatch(itemApplies: string | undefined, scope: 'zone' | 'line'): boolean {
  const a = (itemApplies || 'zone').toLowerCase();
  if (a === 'both') return true;
  return a === scope;
}

function capabilityBadge(cap: string, lang: 'fr' | 'en'): string {
  if (cap === 'real') return lang === 'fr' ? 'Réel' : 'Real';
  if (cap === 'partial') return lang === 'fr' ? 'Partiel' : 'Partial';
  return lang === 'fr' ? 'Bêta' : 'Beta';
}

/** Build grouped ExplanatorySelect options from capabilities/menu (dynamic + health-aware). */
export function behaviorMenuOptions(
  items: CapabilitiesBehaviorMenuItem[],
  scope: 'zone' | 'line',
  lang: 'fr' | 'en',
  opts?: { includeStandard?: boolean },
): ExplanatoryOption[] {
  const out: ExplanatoryOption[] = [];
  if (opts?.includeStandard && scope === 'zone') {
    out.push({
      value: '',
      label: lang === 'fr' ? 'Détection standard (auto)' : 'Standard detection (auto)',
      technicalId: 'zone_enter / zone_exit',
      technology: lang === 'fr' ? 'YOLO + suivi' : 'YOLO + tracking',
      howItWorks:
        lang === 'fr'
          ? 'Entrées et sorties d\'objets dans le polygone.'
          : 'Object enter/exit events in the polygon.',
      stepUtility:
        lang === 'fr'
          ? 'Comportement par défaut si aucun moteur spécialisé.'
          : 'Default when no specialized engine is needed.',
      group: GROUP_LABELS.access[lang],
    });
  }

  const filtered = items.filter((b) => appliesToMatch(b.applies_to, scope));
  for (const b of filtered) {
    const g = GROUP_LABELS[b.group] ?? { fr: b.group, en: b.group };
    const label = lang === 'fr' ? b.label_fr : b.label_en;
    const desc = b.human_description_fr || b.label_fr;
    const emits = (b.emits ?? []).join(', ');
    const readyNote = b.ready
      ? (lang === 'fr' ? 'Prêt à l\'emploi.' : 'Ready to use.')
      : (b.ready_reason_fr || (lang === 'fr' ? 'Prérequis manquants.' : 'Missing prerequisites.'));
    out.push({
      value: b.id,
      label,
      technicalId: `${b.id} → ${emits || '—'}`,
      technology: `${capabilityBadge(b.capability, lang)} · ${b.requires?.join(', ') || (lang === 'fr' ? 'aucun prérequis' : 'no requirements')}`,
      howItWorks: desc,
      stepUtility: readyNote,
      group: g[lang],
      disabled: !b.ready,
      disabledReason: b.ready ? undefined : (b.ready_reason_fr || readyNote),
    });
  }
  return out;
}

/** Resolve behavior metadata for detail panel (catalog static + dynamic menu). */
export function resolveBehaviorMeta(
  behaviorId: string | undefined,
  menuItems: CapabilitiesBehaviorMenuItem[],
  _lang: 'fr' | 'en',
): ZoneBehavior | undefined {
  if (!behaviorId) return getBehavior('');
  const staticB = getBehavior(behaviorId);
  if (staticB) return staticB;
  const dyn = menuItems.find((m) => m.id === behaviorId);
  if (!dyn) return undefined;
  return {
    id: dyn.id,
    group: dyn.group,
    label_fr: dyn.label_fr,
    label_en: dyn.label_en,
    capability: (dyn.capability as ZoneBehavior['capability']) || 'beta',
    human_description_fr: dyn.human_description_fr || dyn.label_fr,
    human_description_en: dyn.label_en,
    emits: dyn.emits ?? [],
    requires: dyn.requires ?? [],
    config_fields: parseConfigFields(dyn.config_fields),
    applies_to: (dyn.applies_to === 'line' ? 'line' : 'zone') as 'zone' | 'line',
  };
}

function parseConfigFields(raw: unknown): ZoneBehavior['config_fields'] {
  if (!Array.isArray(raw)) return [];
  return raw as ZoneBehavior['config_fields'];
}
