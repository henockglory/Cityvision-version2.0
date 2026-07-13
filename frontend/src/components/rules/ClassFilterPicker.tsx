import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import ExplanatorySelect from '@/components/ui/ExplanatorySelect';
import { buildClassFilterOptions } from '@/lib/conditionValueOptions';
import { useModelPack } from '@/hooks/api/queries';

interface ClassFilterPickerProps {
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  compact?: boolean;
}

export default function ClassFilterPicker({ value, onChange, compact = false }: ClassFilterPickerProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.startsWith('en') ? 'en' : 'fr';
  const { data: modelPack } = useModelPack();

  const options = useMemo(
    () =>
      buildClassFilterOptions(
        lang,
        t('rules.studio.classFilterGroups'),
        t('rules.studio.classFilterCoco'),
        modelPack?.detection_classes,
      ),
    [lang, t, modelPack?.detection_classes],
  );

  return (
    <ExplanatorySelect
      compact={compact}
      value={value || ''}
      onChange={onChange}
      options={options}
      placeholder={t('rules.studio.classFilterChoose')}
      searchable
    />
  );
}
