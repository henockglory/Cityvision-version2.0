import type { TFunction } from 'i18next';
import type { CapabilitiesBehaviorMenuItem } from '@/api/client';
import type { ExplanatoryOption } from '@/components/ui/ExplanatorySelect';
import type { RuleCatalogTemplate } from '@/types';
import type { ConditionNode } from '@/lib/conditionTree';
import { cloneCondition, createGroup, createLeaf } from '@/lib/conditionTree';
import type { RuleActivationConfig } from '@/lib/ruleDefinitionBuilder';
import { eventTypeLabel } from '@/lib/conditionValueOptions';

export type ObservationStructureId = string;

export interface ObservationStructureContext {
  lang: 'fr' | 'en';
  activeTemplate: RuleCatalogTemplate;
  templateEventHint?: string;
  linkedBehaviors: CapabilitiesBehaviorMenuItem[];
  activationCfg: RuleActivationConfig;
  t: TFunction;
}

function structureMeta(
  technicalId: string,
  howItWorks: string,
  lang: 'fr' | 'en',
): Pick<ExplanatoryOption, 'technicalId' | 'technology' | 'howItWorks' | 'stepUtility'> {
  return {
    technicalId,
    technology: lang === 'en' ? 'Condition structure' : 'Structure de conditions',
    howItWorks,
    stepUtility:
      lang === 'en'
        ? 'Pre-fills the condition tree — you can still edit every row.'
        : 'Pré-remplit l\'arbre de conditions — chaque ligne reste modifiable.',
  };
}

/** Event types available for OR / N-sur-M patterns (template + compatible behaviors). */
export function collectCompatibleEventTypes(
  templateEventHint: string | undefined,
  linkedBehaviors: CapabilitiesBehaviorMenuItem[],
): string[] {
  const set = new Set<string>();
  if (templateEventHint) set.add(templateEventHint);
  for (const b of linkedBehaviors) {
    for (const e of b.emits ?? []) {
      if (e) set.add(e);
    }
  }
  return [...set].sort();
}

export function buildObservationStructureOptions(ctx: ObservationStructureContext): ExplanatoryOption[] {
  const { lang, activeTemplate, templateEventHint, linkedBehaviors, t } = ctx;
  const isEn = lang === 'en';
  const opts: ExplanatoryOption[] = [
    {
      value: 'manual',
      label: t('rules.studio.observationStructureManual', { defaultValue: 'Configuration manuelle' }),
      group: isEn ? 'General' : 'Général',
      ...structureMeta(
        'manual',
        isEn ? 'Build conditions row by row.' : 'Composez les conditions ligne par ligne.',
        lang,
      ),
    },
  ];

  if (activeTemplate?.definition?.condition) {
    opts.push({
      value: `catalog:${activeTemplate.id}`,
      label: t('rules.studio.observationStructureFromCatalog', {
        defaultValue: 'Depuis le gabarit « {{name}} »',
        name: activeTemplate.name,
      }),
      group: isEn ? 'Catalog template' : 'Gabarit catalogue',
      ...structureMeta(
        activeTemplate.id,
        isEn
          ? `Uses the catalog condition tree for « ${activeTemplate.name} ».`
          : `Reprend l'arbre du gabarit « ${activeTemplate.name} ».`,
        lang,
      ),
    });
  }

  if (templateEventHint) {
    opts.push({
      value: 'pattern:single',
      label: t('rules.studio.observationStructurePatternSingle', {
        defaultValue: 'Un événement (gabarit actuel)',
      }),
      group: isEn ? 'Logic patterns' : 'Patterns logiques',
      ...structureMeta(
        'single_event',
        isEn
          ? `Single event: ${eventTypeLabel(templateEventHint, lang)}`
          : `Événement unique : ${eventTypeLabel(templateEventHint, lang)}`,
        lang,
      ),
    });
  }

  for (const b of linkedBehaviors) {
    const emit = b.emits?.[0];
    if (!emit) continue;
    const label = isEn ? (b.label_en || b.label_fr) : (b.label_fr || b.label_en);
    opts.push({
      value: `behavior:${b.id}`,
      label: t('rules.studio.observationStructureFromBehavior', {
        defaultValue: 'Comptage · {{label}}',
        label,
      }),
      group: isEn ? 'Compatible behaviors' : 'Comportements compatibles',
      ...structureMeta(
        b.id,
        isEn
          ? `Event ${eventTypeLabel(emit, lang)} from behavior ${label}.`
          : `Événement ${eventTypeLabel(emit, lang)} via le comportement ${label}.`,
        lang,
      ),
    });
  }

  const eventCount = collectCompatibleEventTypes(templateEventHint, linkedBehaviors).length;
  if (eventCount >= 2) {
    opts.push({
      value: 'pattern:or',
      label: t('rules.studio.observationStructurePatternOr', {
        defaultValue: 'Plusieurs événements (OU)',
      }),
      group: isEn ? 'Logic patterns' : 'Patterns logiques',
      ...structureMeta(
        'RULE_SET_OR',
        isEn ? 'Count when any selected event type matches.' : 'Compte dès qu\'un des événements sélectionnés correspond.',
        lang,
      ),
    });
    opts.push({
      value: 'pattern:n',
      label: t('rules.studio.observationStructurePatternN', {
        defaultValue: 'Combinaison N-sur-M',
      }),
      group: isEn ? 'Logic patterns' : 'Patterns logiques',
      ...structureMeta(
        'RULE_SET',
        isEn ? 'Count when N distinct event types occur in a time window.' : 'Compte quand N types d\'événements distincts sont observés dans une fenêtre.',
        lang,
      ),
    });
  }

  return opts;
}

function spatialLeaves(cfg: RuleActivationConfig, eventType: string): ConditionNode[] {
  const leaves: ConditionNode[] = [createLeaf('event_type', 'eq', eventType)];
  if (cfg.lineName) leaves.push(createLeaf('line_id', 'eq', cfg.lineName));
  if (cfg.zoneName) leaves.push(createLeaf('zone_id', 'eq', cfg.zoneName));
  if (cfg.classFilter) leaves.push(createLeaf('class_name', 'matches_class', cfg.classFilter));
  return leaves;
}

export function buildOrStructureTree(eventTypes: string[]): ConditionNode {
  return {
    op: 'RULE_SET_OR',
    children: eventTypes.map((et) => createLeaf('event_type', 'eq', et)),
  };
}

export function buildNStructureTree(
  eventTypes: string[],
  minMatches = 2,
  windowSeconds = 300,
): ConditionNode {
  return {
    op: 'RULE_SET',
    min_matches: minMatches,
    window_seconds: windowSeconds,
    key_fields: ['camera_id', 'track_id'],
    children: eventTypes.map((et) => createLeaf('event_type', 'eq', et)),
  };
}

export function applyObservationStructure(
  structureId: ObservationStructureId,
  ctx: ObservationStructureContext,
  selectedEventTypes?: string[],
): ConditionNode | null {
  if (structureId === 'manual') return null;

  const { activeTemplate, templateEventHint, linkedBehaviors, activationCfg } = ctx;

  if (structureId.startsWith('catalog:')) {
    const cond = activeTemplate.definition?.condition as ConditionNode | undefined;
    return cond ? (cloneCondition(cond) ?? null) : null;
  }

  if (structureId.startsWith('behavior:')) {
    const behaviorId = structureId.slice('behavior:'.length);
    const b = linkedBehaviors.find((x) => x.id === behaviorId);
    const emit = b?.emits?.[0];
    if (!emit) return null;
    return createGroup('AND', spatialLeaves(activationCfg, emit));
  }

  if (structureId === 'pattern:single') {
    if (!templateEventHint) return null;
    return createGroup('AND', spatialLeaves(activationCfg, templateEventHint));
  }

  if (structureId === 'pattern:or') {
    const types = selectedEventTypes?.length
      ? selectedEventTypes
      : collectCompatibleEventTypes(templateEventHint, linkedBehaviors);
    if (types.length < 2) return null;
    return buildOrStructureTree(types);
  }

  if (structureId === 'pattern:n') {
    const types = selectedEventTypes?.length
      ? selectedEventTypes
      : collectCompatibleEventTypes(templateEventHint, linkedBehaviors);
    if (types.length < 2) return null;
    return buildNStructureTree(types);
  }

  return null;
}

export function structureNeedsEventPicker(structureId: ObservationStructureId): boolean {
  return structureId === 'pattern:or' || structureId === 'pattern:n';
}
