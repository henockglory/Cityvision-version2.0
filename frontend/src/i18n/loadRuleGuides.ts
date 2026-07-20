import i18n from './index';

const loaded = new Set<string>();

export async function loadRuleGuides(lng?: string): Promise<void> {
  const key = (lng ?? i18n.language ?? 'fr').startsWith('en') ? 'en' : 'fr';
  if (loaded.has(key)) return;

  const mod =
    key === 'en'
      ? await import('./generated/rule-guides-en.json')
      : await import('./generated/rule-guides-fr.json');

  const guides = (mod.default ?? mod) as Record<string, unknown>;
  i18n.addResourceBundle(key, 'translation', { rules: { guides } }, true, true);
  loaded.add(key);
}
