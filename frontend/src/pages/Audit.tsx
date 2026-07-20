import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileText, ShieldCheck, Filter } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import LoadingState from '@/components/ui/LoadingState';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import { useAudit, useVerifyAuditChain } from '@/hooks/api/queries';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';
import { useSound } from '@/hooks/useSound';

const ACTION_FILTERS = [
  '',
  'login',
  'logout',
  'rule.create',
  'rule.update',
  'rule.delete',
  'rule.disable',
  'camera.create',
  'camera.update',
  'zone.create',
  'line.create',
  'alert.archive',
  'alert.create',
];

const actionColors: Record<string, string> = {
  login: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/30',
  logout: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/30',
  'rule.create': 'text-cv-accent bg-cv-accent/10 border-cv-accent/30',
  'rule.update': 'text-amber-400 bg-amber-400/10 border-amber-400/30',
  'rule.delete': 'text-red-400 bg-red-400/10 border-red-400/30',
  'alert.archive': 'text-blue-400 bg-blue-400/10 border-blue-400/30',
  'camera.create': 'text-cv-accent bg-cv-accent/10 border-cv-accent/30',
  'zone.create': 'text-purple-400 bg-purple-400/10 border-purple-400/30',
};

export default function Audit() {
  const { t } = useTranslation();
  const { playClick, playSonar } = useSound();
  const startTour = useAutoPageTour('audit');
  const [actionFilter, setActionFilter] = useState('');
  const { data: audit = [], isLoading, isError, refetch } = useAudit(actionFilter || undefined);
  const verifyChain = useVerifyAuditChain();
  const [chainValid, setChainValid] = useState<boolean | null>(null);

  const runVerify = async () => {
    playClick();
    const res = await verifyChain.mutateAsync();
    setChainValid(res.data.valid);
    if (res.data.valid) playSonar();
  };

  if (isLoading) return <LoadingState />;

  if (isError) {
    return (
      <div>
        <PageHeader title={t('audit.title')} onHelpTour={startTour} />
        <ErrorState onRetry={() => void refetch()} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={t('audit.title')}
        subtitle={t('audit.subtitle', 'Journal immuable signé — traçabilité complète')}
        onHelpTour={startTour}
        actions={
          <button
            type="button"
            onClick={() => void runVerify()}
            disabled={verifyChain.isPending}
            className="cv-btn-secondary text-xs"
          >
            <ShieldCheck className="w-4 h-4" />
            Vérifier l’intégrité
          </button>
        }
      />

      {chainValid !== null && (
        <p
          className={`text-sm mb-4 px-3 py-2 rounded-lg border ${
            chainValid
              ? 'text-emerald-400 border-emerald-400/30 bg-emerald-400/10'
              : 'text-red-400 border-red-400/30 bg-red-400/10'
          }`}
        >
          Chaîne d’audit : {chainValid ? 'intègre ✓' : 'anomalie détectée'}
        </p>
      )}

      <div className="flex items-center gap-3 mb-4">
        <Filter className="w-4 h-4 text-cv-muted" />
        <select
          className="cv-input max-w-xs text-sm"
          value={actionFilter}
          onChange={(e) => {
            playClick();
            setActionFilter(e.target.value);
          }}
        >
          <option value="">Toutes les actions</option>
          {ACTION_FILTERS.filter(Boolean).map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
      </div>

      {audit.length === 0 ? (
        <EmptyState title={t('audit.empty')} hint={t('audit.emptyHint')} icon={FileText} />
      ) : (
        <div id="audit-log" className="cv-card overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-cv-border">
                <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">
                  {t('audit.timestamp')}
                </th>
                <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">
                  User
                </th>
                <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">
                  {t('audit.action')}
                </th>
                <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">
                  {t('audit.resource')}
                </th>
                <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">
                  IP
                </th>
              </tr>
            </thead>
            <tbody>
              {audit.map((entry) => (
                <tr key={entry.id} className="border-b border-cv-border/50 hover:bg-cv-accent/5 transition-colors">
                  <td className="px-5 py-3 text-sm text-cv-muted whitespace-nowrap">
                    {new Date(entry.timestamp).toLocaleString()}
                  </td>
                  <td className="px-5 py-3 text-sm font-medium">{entry.username}</td>
                  <td className="px-5 py-3">
                    <span className={`cv-badge border ${actionColors[entry.action] ?? 'text-cv-muted'}`}>
                      {entry.action}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-sm font-mono text-cv-muted">{entry.resource}</td>
                  <td className="px-5 py-3 text-sm font-mono text-cv-muted">{entry.ip}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
