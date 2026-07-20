import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import fr from './fr.json';
import en from './en.json';
import frToursExtended from './tours-extended.fr.json';
import enToursExtended from './tours-extended.en.json';

function mergeTours(base: Record<string, unknown>, extended: Record<string, unknown>) {
  const baseTours = (base.tours ?? {}) as Record<string, unknown>;
  const extTours = (extended.tours ?? {}) as Record<string, unknown>;
  const merged: Record<string, unknown> = { ...base };
  merged.tours = deepMerge(baseTours, extTours);
  return merged;
}

function deepMerge(
  target: Record<string, unknown>,
  source: Record<string, unknown>,
): Record<string, unknown> {
  const out = { ...target };
  for (const key of Object.keys(source)) {
    const sv = source[key];
    const tv = out[key];
    if (sv && typeof sv === 'object' && !Array.isArray(sv) && tv && typeof tv === 'object' && !Array.isArray(tv)) {
      out[key] = deepMerge(tv as Record<string, unknown>, sv as Record<string, unknown>);
    } else {
      out[key] = sv;
    }
  }
  return out;
}

i18n.use(initReactI18next).init({
  resources: {
    fr: { translation: mergeTours(fr as Record<string, unknown>, frToursExtended as Record<string, unknown>) },
    en: { translation: mergeTours(en as Record<string, unknown>, enToursExtended as Record<string, unknown>) },
  },
  lng: 'fr',
  fallbackLng: 'fr',
  interpolation: { escapeValue: false },
  pluralSeparator: '_',
});

export { loadRuleGuides } from './loadRuleGuides';
export default i18n;
