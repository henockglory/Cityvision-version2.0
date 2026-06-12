import { useTranslation } from 'react-i18next';
import PageHeader from '@/components/ui/PageHeader';
import LoadingState from '@/components/ui/LoadingState';
import { useAudit } from '@/hooks/api/queries';

const actionColors: Record<string, string> = {
  LOGIN: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/30',
  CREATE: 'text-cv-accent bg-cv-accent/10 border-cv-accent/30',
  UPDATE: 'text-amber-400 bg-amber-400/10 border-amber-400/30',
  ACKNOWLEDGE: 'text-blue-400 bg-blue-400/10 border-blue-400/30',
  DELETE: 'text-red-400 bg-red-400/10 border-red-400/30',
};

export default function Audit() {
  const { t } = useTranslation();
  const { data: audit = [], isLoading } = useAudit();

  if (isLoading) return <LoadingState />;

  return (
    <div>
      <PageHeader title={t('audit.title')} />

      <div className="cv-card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-cv-border">
              <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">{t('audit.timestamp')}</th>
              <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">Utilisateur</th>
              <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">{t('audit.action')}</th>
              <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">{t('audit.resource')}</th>
              <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">IP</th>
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
    </div>
  );
}
