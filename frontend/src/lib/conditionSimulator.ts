import type { TFunction } from 'i18next';
import { evaluateConditionNode } from '@/lib/conditionEvaluator';
import { eventTypeLabel } from '@/lib/conditionValueOptions';
import type { ConditionNode } from '@/lib/conditionTree';
import { isGroupNode } from '@/lib/conditionTree';

export type ScenarioRow = {
  id: string;
  label: string;
  payload: Record<string, unknown>;
  /** Force displayed result (e.g. full sequence explanation). */
  forceMatches?: boolean;
  whyYes?: string;
  whyNo?: string;
};

export type SimulatedRow = ScenarioRow & {
  matches: boolean;
  why: string;
};

function langOf(t: TFunction, lang?: 'fr' | 'en'): 'fr' | 'en' {
  if (lang) return lang;
  return t('rules.studio.simulator.yes', { lng: 'en' }) === 'Yes' ? 'en' : 'fr';
}

function collectLeaves(node: ConditionNode): ConditionNode[] {
  if (isGroupNode(node)) {
    return (node.children ?? []).flatMap(collectLeaves);
  }
  return [node];
}

function leafPayload(leaf: ConditionNode): Record<string, unknown> {
  if (!leaf.field || leaf.value === undefined || leaf.value === '') return {};
  return { [leaf.field]: leaf.value };
}

function mergePayloads(parts: Record<string, unknown>[]): Record<string, unknown> {
  return Object.assign({}, ...parts);
}

function buildPassPayload(node: ConditionNode): Record<string, unknown> {
  const op = String(node.op ?? 'AND').toUpperCase();
  if (!isGroupNode(node)) return leafPayload(node);
  if (op === 'OR' && node.children?.length) {
    return buildPassPayload(node.children[0]);
  }
  if (node.children?.length) {
    return mergePayloads(node.children.map(buildPassPayload));
  }
  return {};
}

function alternateValue(field: string, current: unknown): unknown {
  if (field === 'event_type') return current === 'zone_enter' ? 'line_cross' : 'zone_enter';
  if (field === 'class_name' || field === 'class_filter') return current === 'person' ? 'car' : 'person';
  if (field === 'direction') return current === 'in' ? 'out' : 'in';
  if (field === 'zone_id' || field === 'line_id') return '__autre__';
  return '__autre__';
}

function describeLeaf(leaf: ConditionNode, t: TFunction, lang: 'fr' | 'en'): string {
  const field = leaf.field ?? '';
  const val = leaf.value;
  if (field === 'event_type' && val != null) {
    return eventTypeLabel(String(val), lang);
  }
  if (field === 'class_name' || field === 'class_filter') {
    return String(val);
  }
  const fieldLabel = t(`rules.narrative.fields.${field}`, field);
  return `${fieldLabel} = ${String(val ?? '')}`;
}

function describeTreeSummary(node: ConditionNode, t: TFunction, lang: 'fr' | 'en'): string {
  const op = String(node.op ?? 'AND').toUpperCase();
  if (!isGroupNode(node)) return describeLeaf(node, t, lang);
  const parts = (node.children ?? []).map((c) => describeTreeSummary(c, t, lang));
  if (op === 'SEQUENCE') {
    return lang === 'fr' ? parts.join(' → puis ') : parts.join(' → then ');
  }
  const join = op === 'OR' || op === 'OU' ? (lang === 'fr' ? ' ou ' : ' or ') : lang === 'fr' ? ' et ' : ' and ';
  return parts.join(join);
}

function buildSequenceScenarios(node: ConditionNode, t: TFunction, lang: 'fr' | 'en'): ScenarioRow[] {
  const steps = node.children ?? [];
  const rows: ScenarioRow[] = [];

  steps.forEach((step, i) => {
    const payload = buildPassPayload(step);
    const desc = describeTreeSummary(step, t, lang);
    rows.push({
      id: `seq-step-${i}`,
      label:
        lang === 'fr'
          ? `Étape ${i + 1} seule : ${desc}`
          : `Step ${i + 1} only: ${desc}`,
      payload,
      whyNo:
        lang === 'fr'
          ? `L'étape ${i + 1} est détectée, mais la séquence complète n'est pas achevée — pas d'alerte pour l'instant.`
          : `Step ${i + 1} detected, but the full sequence is not complete — no alert yet.`,
    });
  });

  const summary = describeTreeSummary(node, t, lang);
  rows.push({
    id: 'seq-full',
    label:
      lang === 'fr'
        ? `Séquence complète : ${summary}`
        : `Full sequence: ${summary}`,
    payload: {},
    forceMatches: true,
    whyYes:
      lang === 'fr'
        ? 'Toutes les étapes se produisent dans l\'ordre et dans la fenêtre temporelle — la règle déclenche une alerte.'
        : 'All steps occur in order within the time window — the rule triggers an alert.',
  });

  const failPayload: Record<string, unknown> = { event_type: 'zone_enter' };
  rows.push({
    id: 'seq-unrelated',
    label:
      lang === 'fr'
        ? 'Événement sans lien (ex. simple entrée en zone)'
        : 'Unrelated event (e.g. zone entry only)',
    payload: failPayload,
    whyNo:
      lang === 'fr'
        ? 'Aucune étape de la séquence n\'est reconnue — pas d\'alerte.'
        : 'No sequence step is recognized — no alert.',
  });

  return rows;
}

function buildAndOrScenarios(node: ConditionNode, t: TFunction, lang: 'fr' | 'en'): ScenarioRow[] {
  const passPayload = buildPassPayload(node);
  const summary = describeTreeSummary(node, t, lang);
  const op = String(node.op ?? 'AND').toUpperCase();
  const isOr = op === 'OR' || op === 'OU';

  const rows: ScenarioRow[] = [
    {
      id: 'pass',
      label:
        lang === 'fr'
          ? `Scénario qui déclenche l'alerte : ${summary}`
          : `Scenario that triggers the alert: ${summary}`,
      payload: passPayload,
      whyYes:
        lang === 'fr'
          ? isOr
            ? 'Au moins une branche de la condition est remplie — la règle déclenche une alerte.'
            : 'Toutes les conditions sont remplies simultanément — la règle déclenche une alerte.'
          : isOr
            ? 'At least one condition branch is satisfied — the rule triggers an alert.'
            : 'All conditions are met at once — the rule triggers an alert.',
    },
  ];

  const leaves = collectLeaves(node);
  const failLeaf = leaves.find((l) => l.field === 'event_type') ?? leaves[0];
  if (failLeaf?.field) {
    const failPayload = { ...passPayload, [failLeaf.field]: alternateValue(failLeaf.field, failLeaf.value) };
    rows.push({
      id: 'fail-primary',
      label:
        lang === 'fr'
          ? failLeaf.field === 'event_type'
            ? `Événement différent (pas « ${eventTypeLabel(String(failLeaf.value), lang)} »)`
            : `Condition non remplie (${describeLeaf(failLeaf, t, lang)} attendu)`
          : `Different event (not « ${eventTypeLabel(String(failLeaf.value), lang)} »)`,
      payload: failPayload,
      whyNo:
        lang === 'fr'
          ? 'Une condition clé n\'est pas remplie — la règle ne se déclenche pas.'
          : 'A key condition is not met — the rule does not trigger.',
    });
  }

  if (leaves.some((l) => l.field === 'class_name' || l.field === 'class_filter')) {
    const classLeaf = leaves.find((l) => l.field === 'class_name' || l.field === 'class_filter');
    if (classLeaf?.field) {
      rows.push({
        id: 'fail-class',
        label:
          lang === 'fr'
            ? `Mauvaise classe d'objet (ex. véhicule au lieu de personne)`
            : `Wrong object class (e.g. vehicle instead of person)`,
        payload: {
          ...passPayload,
          [classLeaf.field]: alternateValue(classLeaf.field, classLeaf.value),
        },
        whyNo:
          lang === 'fr'
            ? 'La classe d\'objet détectée ne correspond pas au filtre — pas d\'alerte.'
            : 'Detected object class does not match the filter — no alert.',
      });
    }
  }

  return rows.slice(0, 4);
}

/** Build coherent demo scenarios from the live condition tree. */
export function buildScenariosFromTree(
  tree: ConditionNode,
  t: TFunction,
  lang?: 'fr' | 'en',
): ScenarioRow[] {
  if (!tree) return [];
  const lng = langOf(t, lang);
  const op = String(tree.op ?? 'AND').toUpperCase();

  if (op === 'SEQUENCE') {
    return buildSequenceScenarios(tree, t, lng);
  }
  if (isGroupNode(tree)) {
    return buildAndOrScenarios(tree, t, lng);
  }
  return buildAndOrScenarios({ op: 'AND', children: [tree] }, t, lng);
}

export function simulateScenarios(
  tree: ConditionNode,
  scenarios: ScenarioRow[],
  t: TFunction,
): SimulatedRow[] {
  return scenarios.map((s) => {
    const matches = s.forceMatches ?? evaluateConditionNode(tree, s.payload);
    const why = matches
      ? (s.whyYes ?? t('rules.studio.simulator.whyYes'))
      : (s.whyNo ?? t('rules.studio.simulator.whyNo'));
    return { ...s, matches, why };
  });
}

/** @deprecated Use buildScenariosFromTree — kept for scripts. */
export function parseGuideScenarios(
  templateId: string,
  t: TFunction,
): ScenarioRow[] {
  const raw = t(`rules.guides.${templateId}.scenarios`, { returnObjects: true, defaultValue: [] });
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item): item is Record<string, unknown> => item != null && typeof item === 'object')
    .map((item, i) => ({
      id: String(item.id ?? `s-${i}`),
      label: String(item.label ?? ''),
      payload: (item.payload as Record<string, unknown>) ?? {},
    }))
    .filter((s) => s.label && Object.keys(s.payload).length > 0);
}
