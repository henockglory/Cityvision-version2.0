import { useTranslation } from 'react-i18next';
import { CLASS_GROUPS, COCO_CLASSES, classLabel } from '@/lib/detectionClasses';

interface ClassFilterPickerProps {
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}

export default function ClassFilterPicker({ value, onChange, required }: ClassFilterPickerProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.startsWith('en') ? 'en' : 'fr';

  return (
    <select
      className="cv-input w-full"
      value={value || ''}
      required={required}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{t('rules.studio.classFilterChoose')}</option>
      <optgroup label={t('rules.studio.classFilterGroups')}>
        {CLASS_GROUPS.map((g) => (
          <option key={g.id} value={g.id}>
            {classLabel(g.id, lang)}
          </option>
        ))}
      </optgroup>
      <optgroup label={t('rules.studio.classFilterCoco')}>
        {COCO_CLASSES.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </optgroup>
    </select>
  );
}
