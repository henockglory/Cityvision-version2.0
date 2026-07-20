import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { GitBranch, AlertTriangle } from 'lucide-react';
import type { ZoneRuleLink } from '@/lib/zoneRuleLinks';

export default function ZoneRuleLinkPanel({
  zoneName,
  links,
}: {
  zoneName: string;
  links: ZoneRuleLink[];
}) {
  const { t } = useTranslation();
  if (!zoneName) return null;
  return (
    <div className="rounded-lg border border-cv-border/50 bg-cv-deep/30 p-3 space-y-2">
      <p className="text-xs font-medium text-cv-text flex items-center gap-1.5">
        <GitBranch className="w-3.5 h-3.5 text-cv-accent" />
        {t('zoneEditor.linkedRules', { defaultValue: 'Règles liées' })}
      </p>
      {links.length === 0 ? (
        <p className="text-[11px] text-cv-muted">
          {t('zoneEditor.noLinkedRules', { defaultValue: 'Aucune règle ne référence cette zone.' })}
          {' '}
          <Link to="/rules" className="text-cv-accent underline">{t('zoneEditor.createRule', { defaultValue: 'Créer une règle' })}</Link>
        </p>
      ) : (
        <ul className="text-[11px] space-y-1.5">
          {links.map((l) => (
            <li key={l.ruleId} className="flex items-start gap-2">
              <span className={l.misconfigured ? 'text-amber-400' : l.enabled ? 'text-emerald-400' : 'text-cv-muted'}>
                {l.misconfigured ? '⚠' : '●'}
              </span>
              <span className="min-w-0">
                <span className="text-cv-text/90">{l.ruleName}</span>
                <span className="text-cv-muted"> · {l.templateId}</span>
                {l.eventType ? (
                  <span className="text-cv-muted/70"> · {l.eventType}</span>
                ) : null}
                {l.misconfigured && (
                  <span className="flex items-start gap-1 text-amber-400 mt-0.5">
                    <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />
                    <span>
                      {l.misconfiguredReason ?? t('zoneEditor.misconfigured', { defaultValue: 'Désynchronisé' })}
                      {' '}
                      <Link to="/rules" className="underline text-cv-accent">
                        {t('zoneEditor.fixRule', { defaultValue: 'Corriger' })}
                      </Link>
                    </span>
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
