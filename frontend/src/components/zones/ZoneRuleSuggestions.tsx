import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { BookOpen, X, Zap } from 'lucide-react';
import { capabilitiesApi, type CapabilitiesBehaviorMenuItem } from '@/api/client';
import { useRuleCatalog } from '@/hooks/api/queries';
import { useAuthStore } from '@/stores/authStore';
import { templateIdsForBehavior } from '@/lib/zoneRuleLinks';

export interface SavedZoneSuggestion {
  name: string;
  behavior?: string;
  cameraId: string;
}

interface ZoneRuleSuggestionsProps {
  savedZones: SavedZoneSuggestion[];
  onDismiss: () => void;
  onConfigureTemplate: (templateId: string) => void;
}

export default function ZoneRuleSuggestions({
  savedZones,
  onDismiss,
  onConfigureTemplate,
}: ZoneRuleSuggestionsProps) {
  const { t } = useTranslation();
  const orgId = useAuthStore((s) => s.orgId);
  const catalog = useRuleCatalog();
  const [behaviors, setBehaviors] = useState<CapabilitiesBehaviorMenuItem[]>([]);

  useEffect(() => {
    if (!orgId) return;
    void capabilitiesApi.menu(orgId)
      .then((r) => setBehaviors(r.data.behaviors ?? []))
      .catch(() => setBehaviors([]));
  }, [orgId]);

  const suggestionsByZone = useMemo(() => {
    const templates = catalog.data ?? [];
    return savedZones.map((zone) => {
      const templateIds = templateIdsForBehavior(zone.behavior, behaviors);
      const compatible = templates.filter(
        (tpl) => templateIds.includes(tpl.id) && tpl.supported !== false,
      );
      return { zone, templates: compatible };
    }).filter((row) => row.templates.length > 0);
  }, [savedZones, behaviors, catalog.data]);

  if (suggestionsByZone.length === 0) return null;

  return (
    <div className="mb-4 rounded-lg border border-cv-accent/30 bg-cv-accent/5 p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-cv-text flex items-center gap-2">
          <Zap className="w-4 h-4 text-cv-accent shrink-0" />
          {t('zoneEditor.ruleSuggestionsTitle', { defaultValue: 'Règles compatibles avec vos zones' })}
        </p>
        <button
          type="button"
          className="cv-btn-ghost p-1 rounded"
          onClick={onDismiss}
          aria-label={t('common.close', { defaultValue: 'Fermer' })}
        >
          <X className="w-4 h-4" />
        </button>
      </div>
      <p className="text-xs text-cv-muted">
        {t('zoneEditor.ruleSuggestionsHint', {
          defaultValue: 'Ces modèles de règle émettent les événements produits par le comportement de zone que vous venez d\'enregistrer.',
        })}
      </p>
      <div className="space-y-3">
        {suggestionsByZone.map(({ zone, templates }) => (
          <div key={`${zone.cameraId}-${zone.name}`} className="space-y-1.5">
            <p className="text-xs font-medium text-cv-text/90">
              {zone.name}
              {zone.behavior ? (
                <span className="text-cv-muted font-normal"> · {zone.behavior}</span>
              ) : null}
            </p>
            <ul className="text-[11px] space-y-1">
              {templates.map((tpl) => (
                <li key={tpl.id} className="flex items-center gap-2">
                  <BookOpen className="w-3 h-3 text-cv-accent shrink-0" />
                  <button
                    type="button"
                    className="text-cv-accent underline text-left"
                    onClick={() => onConfigureTemplate(tpl.id)}
                  >
                    {tpl.name}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-cv-muted">
        {t('zoneEditor.ruleSuggestionsCatalog', { defaultValue: 'Ou parcourez le' })}{' '}
        <Link to="/rules" className="text-cv-accent underline">{t('zoneEditor.ruleSuggestionsCatalogLink', { defaultValue: 'catalogue de règles' })}</Link>
      </p>
    </div>
  );
}
