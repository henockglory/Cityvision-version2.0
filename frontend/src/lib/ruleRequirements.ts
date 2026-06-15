import type { RuleCatalogTemplate } from '@/types';

export type BindingKind =
  | 'camera'
  | 'zone'
  | 'line'
  | 'duration'
  | 'watchlist'
  | 'plate'
  | 'speed_limit';

export interface RuleBindingSpec {
  required: BindingKind[];
  optional: BindingKind[];
  hints: Partial<Record<BindingKind, string>>;
}

type CondNode = {
  op?: string;
  field?: string;
  value?: unknown;
  children?: CondNode[];
};

function walkCondition(node: CondNode | undefined, visit: (n: CondNode) => void) {
  if (!node) return;
  visit(node);
  for (const c of node.children ?? []) walkCondition(c, visit);
}

function tplText(tpl: RuleCatalogTemplate): string {
  return `${tpl.id} ${tpl.name} ${tpl.category} ${tpl.description ?? ''}`.toLowerCase();
}

/** Détermine quels paramètres l'utilisateur doit renseigner avant activation. */
export function analyzeRuleBindings(tpl: RuleCatalogTemplate): RuleBindingSpec {
  const required = new Set<BindingKind>(['camera']);
  const optional = new Set<BindingKind>();
  const hints: Partial<Record<BindingKind, string>> = {};
  const def = tpl.definition as { condition?: CondNode };
  const text = tplText(tpl);

  walkCondition(def.condition, (node) => {
    const op = String(node.op ?? '').toLowerCase();
    const field = String(node.field ?? '').toLowerCase();

    if (op === 'in_zone' || field === 'zone_id') {
      required.add('zone');
      hints.zone = 'Zone dessinée dans l’éditeur — le nom doit correspondre exactement.';
    }
    if (op === 'cross_line' || field === 'line_id') {
      required.add('line');
      hints.line = 'Ligne de comptage/franchissement dessinée sur la caméra.';
    }
    if (field === 'duration_seconds' && (op === 'gt' || op === 'lt' || op === 'gte' || op === 'lte')) {
      required.add('duration');
      hints.duration = 'Durée minimale (secondes) avant déclenchement.';
    }
    if (field.includes('speed') || field === 'speed_kmh') {
      optional.add('speed_limit');
      hints.speed_limit = 'Seuil vitesse (km/h) — nécessite calibration caméra.';
    }
  });

  if (
    text.includes('liste de surveillance') ||
    text.includes('watchlist') ||
    tpl.id.includes('watchlist')
  ) {
    required.add('watchlist');
    hints.watchlist = 'Liste de visages de surveillance — au moins un profil requis.';
  }

  if (
    text.includes('plaque bloquée') ||
    text.includes('plaque autorisée') ||
    (text.includes('plaque') && (text.includes('bloqu') || text.includes('autoris') || text.includes('whitelist')))
  ) {
    required.add('plate');
    hints.plate = 'Liste de plaques (autorisées / bloquées) — à définir dans Paramètres → Identité.';
  }

  if (tpl.category === 'security' && text.includes('intrusion')) {
    required.add('zone');
  }

  if (text.includes('loitering') || text.includes('présence prolongée')) {
    required.add('zone');
    if (!required.has('duration')) required.add('duration');
  }

  return {
    required: [...required],
    optional: [...optional],
    hints,
  };
}

export function bindingLabel(kind: BindingKind): string {
  const labels: Record<BindingKind, string> = {
    camera: 'Caméra',
    zone: 'Zone virtuelle',
    line: 'Ligne de franchissement',
    duration: 'Durée (secondes)',
    watchlist: 'Liste de surveillance (visages)',
    plate: 'Liste de plaques',
    speed_limit: 'Seuil vitesse (km/h)',
  };
  return labels[kind];
}
