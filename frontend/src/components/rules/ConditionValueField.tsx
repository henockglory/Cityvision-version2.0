import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import ClassFilterPicker from '@/components/rules/ClassFilterPicker';
import ExplanatorySelect from '@/components/ui/ExplanatorySelect';
import {
  buildDirectionOptions,
  buildEventTypeOptions,
  buildLineOptions,
  buildZoneOptions,
} from '@/lib/conditionValueOptions';

export interface SpatialContext {
  zones: Array<{ id: string; name: string }>;
  lines: Array<{ id: string; name: string }>;
  loadingSpatial?: boolean;
}

interface ConditionValueFieldProps {
  field: string;
  value: unknown;
  onChange: (value: unknown) => void;
  spatial?: SpatialContext;
  templateEventHint?: string;
  className?: string;
}

export default function ConditionValueField({
  field,
  value,
  onChange,
  spatial,
  templateEventHint,
  className = 'flex-1 min-w-[140px]',
}: ConditionValueFieldProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.startsWith('en') ? 'en' : 'fr';

  const eventOptions = useMemo(() => buildEventTypeOptions(lang), [lang]);
  const directionOptions = useMemo(() => buildDirectionOptions(lang), [lang]);
  const zoneOptions = useMemo(
    () => buildZoneOptions(spatial?.zones ?? [], lang),
    [spatial?.zones, lang],
  );
  const lineOptions = useMemo(
    () => buildLineOptions(spatial?.lines ?? [], lang),
    [spatial?.lines, lang],
  );

  if (field === 'event_type') {
    return (
      <ExplanatorySelect
        className={className}
        compact
        value={String(value ?? templateEventHint ?? '')}
        onChange={(v) => onChange(v)}
        options={eventOptions}
        placeholder={t('rules.studio.eventTypeChoose', { defaultValue: '— Choisir un événement —' })}
        emptyLabel={t('common.noResults', { defaultValue: 'Aucun résultat' })}
      />
    );
  }

  if (field === 'zone_id') {
    if (spatial?.loadingSpatial) {
      return <span className="text-xs text-cv-muted">{t('common.loading')}</span>;
    }
    if (!spatial?.zones.length) {
      return (
        <span className="text-xs text-amber-500">
          {t('rules.studio.noZones', { defaultValue: 'Aucune zone — configurez à l’étape 1' })}
        </span>
      );
    }
    return (
      <ExplanatorySelect
        className={className}
        compact
        searchable={zoneOptions.length > 8}
        value={String(value ?? '')}
        onChange={(v) => onChange(v)}
        options={zoneOptions}
        placeholder={t('rules.studio.zoneChoose', { defaultValue: '— Choisir une zone —' })}
      />
    );
  }

  if (field === 'line_id') {
    if (spatial?.loadingSpatial) {
      return <span className="text-xs text-cv-muted">{t('common.loading')}</span>;
    }
    if (!spatial?.lines.length) {
      return (
        <span className="text-xs text-amber-500">
          {t('rules.studio.noLines', { defaultValue: 'Aucune ligne — configurez à l’étape 1' })}
        </span>
      );
    }
    return (
      <ExplanatorySelect
        className={className}
        compact
        searchable={lineOptions.length > 8}
        value={String(value ?? '')}
        onChange={(v) => onChange(v)}
        options={lineOptions}
        placeholder={t('rules.studio.lineChoose', { defaultValue: '— Choisir une ligne —' })}
      />
    );
  }

  if (field === 'class_filter' || field === 'class_name') {
    return (
      <div className={`${className} min-w-[160px]`}>
        <ClassFilterPicker value={String(value ?? '')} onChange={onChange} compact />
      </div>
    );
  }

  if (field === 'direction') {
    return (
      <ExplanatorySelect
        className={className}
        compact
        value={String(value ?? 'both')}
        onChange={(v) => onChange(v)}
        options={directionOptions}
        searchable={false}
      />
    );
  }

  const numericFields: Record<string, { min?: number; max?: number; step?: number }> = {
    duration_seconds: { min: 1, max: 86400, step: 1 },
    speed_kmh: { min: 1, max: 300, step: 1 },
    confidence: { min: 0, max: 1, step: 0.05 },
  };

  const numCfg = numericFields[field];
  const inputClass = 'cv-input text-xs py-1 flex-1 min-w-[100px]';
  if (numCfg) {
    return (
      <input
        type="number"
        className={inputClass}
        min={numCfg.min}
        max={numCfg.max}
        step={numCfg.step}
        value={value != null && value !== '' ? Number(value) : ''}
        onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
        placeholder={t('rules.studio.valuePlaceholder')}
      />
    );
  }

  return (
    <input
      className={inputClass}
      value={value != null ? String(value) : ''}
      onChange={(e) => onChange(e.target.value)}
      placeholder={t('rules.studio.valuePlaceholder')}
    />
  );
}
