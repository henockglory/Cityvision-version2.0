import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import ExplanatorySelect from '@/components/ui/ExplanatorySelect';
import { buildClassFilterOptions } from '@/lib/conditionValueOptions';

interface ClassFilterPickerProps {
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  compact?: boolean;
}

export default function ClassFilterPicker({ value, onChange, compact = false }: ClassFilterPickerProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.startsWith('en') ? 'en' : 'fr';

  const options = useMemo(
    () =>
      buildClassFilterOptions(
        lang,
        t('rules.studio.classFilterGroups'),
        t('rules.studio.classFilterCoco'),
      ),
    [lang, t],
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
