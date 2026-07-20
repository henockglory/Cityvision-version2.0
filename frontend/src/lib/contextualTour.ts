import { type DriveStep, type Driver } from 'driver.js';
import { buildTourDescription, createTourDriver, runTour } from '@/lib/tourEngine';

type TFn = (key: string, opts?: Record<string, unknown>) => string;

export interface FieldTourOptions {
  helpKey?: string;
  /** Texte court affiché si aucune clé i18n enrichie n'existe. */
  content?: string;
}

function resolveFieldKeys(helpKey: string | undefined, t: TFn, content?: string) {
  const prefix = helpKey ? `tours.fields.${helpKey}` : null;
  const titleKey = prefix ? `${prefix}.title` : 'tours.common.fieldTitle';
  const title = t(titleKey, { defaultValue: t('tours.common.fieldTitle') });
  const descKey = prefix ? `${prefix}.desc` : '';
  const descFromKey = descKey ? t(descKey, { defaultValue: '' }) : '';
  const descText = descFromKey || content || '';
  const tipKey = prefix ? `${prefix}.tip` : undefined;
  const stepsKey = prefix ? `${prefix}.steps` : undefined;
  const tip = tipKey ? t(tipKey, { defaultValue: '' }) : '';
  const hasTip = Boolean(tip);
  const steps = stepsKey ? t(stepsKey, { returnObjects: true }) : [];
  const hasSteps = Array.isArray(steps) && steps.length > 0;
  return {
    title,
    description: buildTourDescription(t, descKey, {
      descText,
      tipKey: hasTip ? tipKey : undefined,
      stepsKey: hasSteps ? stepsKey : undefined,
    }),
  };
}

export function buildFieldTourSteps(
  anchor: Element | string,
  t: TFn,
  opts: FieldTourOptions,
): DriveStep[] {
  const { title, description } = resolveFieldKeys(opts.helpKey, t, opts.content);
  return [{
    element: anchor,
    popover: {
      title,
      description,
      side: 'bottom',
    },
  }];
}

let fieldDriver: Driver | null = null;

/** Mini-tutoriel contextuel (1 étape riche) — ne marque pas un tour de page comme complété. */
export function runFieldTour(
  anchor: Element | string,
  t: TFn,
  opts: FieldTourOptions,
): boolean {
  const steps = buildFieldTourSteps(anchor, t, opts);
  fieldDriver?.destroy();
  fieldDriver = createTourDriver({ t });
  return runTour(fieldDriver, steps);
}

export function destroyFieldTour() {
  fieldDriver?.destroy();
  fieldDriver = null;
}
