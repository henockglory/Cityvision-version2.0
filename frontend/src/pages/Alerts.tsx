import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Bell, Camera, Workflow, Archive, Filter, ChevronRight, Film } from 'lucide-react';
import PageShell from '@/components/ui/PageShell';
import SeverityBadge from '@/components/ui/SeverityBadge';
import EvidenceViewer from '@/components/evidence/EvidenceViewer';
import { evidenceThumbnailUrl, parseEvidenceSnapshot } from '@/lib/evidence';
import LoadingState from '@/components/ui/LoadingState';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import ModalPortal from '@/components/ui/ModalPortal';
import { useAlerts, useArchiveAlert, useCameras, useRules } from '@/hooks/api/queries';
import { useSound } from '@/hooks/useSound';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';
import type { AlertFilters } from '@/types';

export default function Alerts() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const startTour = useAutoPageTour('alerts');
  const [statusFilter, setStatusFilter] = useState<'open' | 'archived' | 'all'>('open');
  const [severity, setSeverity] = useState('');
  const [cameraId, setCameraId] = useState('');
  const [ruleId, setRuleId] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const filters: AlertFilters = useMemo(() => {
    const f: AlertFilters = { limit: 200 };
    if (statusFilter !== 'all') f.status = statusFilter;
    if (severity) f.severity = severity;
    if (cameraId) f.cameraId = cameraId;
    if (ruleId) f.ruleId = ruleId;
    if (fromDate) f.from = new Date(fromDate).toISOString();
    if (toDate) f.to = new Date(toDate).toISOString();
    return f;
  }, [statusFilter, severity, cameraId, ruleId, fromDate, toDate]);

  const { data: alerts = [], isLoading, isError, refetch } = useAlerts(filters);
  const { data: cameras = [] } = useCameras();
  const { data: rules = [] } = useRules();
  const archive = useArchiveAlert();
  const [archiveId, setArchiveId] = useState<string | null>(null);
  const [comment, setComment] = useState('');

  const selected = alerts.find((a) => a.id === selectedId) ?? alerts[0] ?? null;

  if (isLoading) return <LoadingState />;

  if (isError) {
    return (
      <PageShell title={t('alerts.title')}>
        <ErrorState onRetry={() => void refetch()} />
      </PageShell>
    );
  }

  const archiveTarget = archiveId ? alerts.find((a) => a.id === archiveId) : null;

  return (
    <PageShell
      title={t('alerts.title')}
      onHelpTour={startTour}
      actions={
        <div className="flex gap-2 flex-wrap">
          {(['open', 'archived', 'all'] as const).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => { playClick(); setStatusFilter(f); }}
              className={`cv-btn-secondary text-xs ${statusFilter === f ? 'border-cv-accent/40' : ''}`}
            >
              {f === 'open' ? 'Ouvertes' : f === 'archived' ? 'Archivées' : t('alerts.all')}
            </button>
          ))}
        </div>
      }
    >
      <div id="alerts-filters" className="cv-card p-4 flex flex-wrap gap-3 items-end">
        <Filter className="w-4 h-4 text-cv-muted mb-2" />
        <div>
          <label className="cv-label text-xs">Sévérité</label>
          <select className="cv-input text-xs" value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="">Toutes</option>
            <option value="low">Faible</option>
            <option value="medium">Moyenne</option>
            <option value="high">Élevée</option>
            <option value="critical">Critique</option>
          </select>
        </div>
        <div>
          <label className="cv-label text-xs">Caméra</label>
          <select className="cv-input text-xs" value={cameraId} onChange={(e) => setCameraId(e.target.value)}>
            <option value="">Toutes</option>
            {cameras.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="cv-label text-xs">Règle</label>
          <select className="cv-input text-xs" value={ruleId} onChange={(e) => setRuleId(e.target.value)}>
            <option value="">Toutes</option>
            {rules.map((r) => (
              <option key={r.id} value={r.id}>{r.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="cv-label text-xs">Du</label>
          <input type="date" className="cv-input text-xs" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
        </div>
        <div>
          <label className="cv-label text-xs">Au</label>
          <input type="date" className="cv-input text-xs" value={toDate} onChange={(e) => setToDate(e.target.value)} />
        </div>
      </div>

      {alerts.length === 0 ? (
        <EmptyState title={t('alerts.empty')} hint={t('alerts.emptyHint')} icon={Bell} />
      ) : (
        <div className="grid lg:grid-cols-5 gap-4">
          <div className="lg:col-span-2 relative pl-6 border-l border-cv-border/60 space-y-3 ml-2 max-h-[70vh] overflow-y-auto">
            {alerts.map((alert) => (
              <button
                key={alert.id}
                type="button"
                onClick={() => { playClick(); setSelectedId(alert.id); }}
                className={`relative w-full text-left ${selected?.id === alert.id ? '' : 'opacity-90'}`}
              >
                <span
                  className={`absolute -left-[1.65rem] top-5 w-3 h-3 rounded-full border-2 border-cv-surface ${
                    alert.acknowledged ? 'bg-cv-muted' : 'bg-cv-accent'
                  }`}
                />
                <div className={`cv-card p-3 ${selected?.id === alert.id ? 'ring-1 ring-cv-accent/50' : ''} ${!alert.acknowledged ? 'border-l-2 border-l-cv-accent' : ''}`}>
                  <div className="flex items-start gap-2">
                    {evidenceThumbnailUrl(parseEvidenceSnapshot(alert.evidenceSnapshot)) ? (
                      <img
                        src={evidenceThumbnailUrl(parseEvidenceSnapshot(alert.evidenceSnapshot))}
                        alt=""
                        className="w-12 h-12 rounded object-cover shrink-0 border border-cv-border/50"
                      />
                    ) : (
                      <span className="w-12 h-12 rounded bg-cv-deep/60 border border-cv-border/40 flex items-center justify-center shrink-0">
                        <Film className="w-4 h-4 text-cv-muted" />
                      </span>
                    )}
                    <SeverityBadge severity={alert.severity} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{alert.message}</p>
                      <p className="text-xs text-cv-muted mt-1">{new Date(alert.timestamp).toLocaleString()}</p>
                    </div>
                    <ChevronRight className="w-4 h-4 text-cv-muted shrink-0" />
                  </div>
                </div>
              </button>
            ))}
          </div>

          {selected && (
            <div className="lg:col-span-3 cv-card p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <SeverityBadge severity={selected.severity} />
                  <h2 className="font-display text-lg font-semibold mt-2">{selected.message}</h2>
                  <p className="text-xs text-cv-muted mt-1">{new Date(selected.timestamp).toLocaleString()}</p>
                </div>
                {!selected.acknowledged ? (
                  <button
                    type="button"
                    onClick={() => { playClick(); setArchiveId(selected.id); setComment(''); }}
                    disabled={archive.isPending}
                    className="cv-btn-secondary text-xs shrink-0"
                  >
                    <Archive className="w-3.5 h-3.5" />
                    Archiver
                  </button>
                ) : (
                  <span className="text-xs text-cv-muted inline-flex items-center gap-1">
                    <Archive className="w-3 h-3" />
                    Archivée
                  </span>
                )}
              </div>

              <div className="mt-4 p-4 rounded-xl bg-cv-surface/40 border border-cv-border/60">
                <EvidenceViewer evidence={selected.evidenceSnapshot} cameraId={selected.cameraId} />
              </div>

              <div className="flex flex-wrap gap-3 mt-4 text-sm text-cv-muted">
                <span className="inline-flex items-center gap-1"><Camera className="w-3.5 h-3.5" />{selected.cameraName}</span>
                {selected.ruleName && (
                  <span className="inline-flex items-center gap-1"><Workflow className="w-3.5 h-3.5" />{selected.ruleName}</span>
                )}
              </div>

              {selected.acknowledged && selected.archiveComment && (
                <p className="mt-3 text-sm p-3 rounded-lg bg-cv-surface border border-cv-border">
                  <span className="text-cv-muted">Commentaire d&apos;archivage : </span>
                  {selected.archiveComment}
                </p>
              )}

              <div className="flex gap-2 mt-2">
                {selected.cameraId && (
                  <Link to={`/live?camera=${selected.cameraId}`} className="cv-btn-ghost text-xs py-1">Voir live</Link>
                )}
                {selected.ruleId && (
                  <Link to="/rules" className="cv-btn-ghost text-xs py-1">Voir règles</Link>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {archiveId && archiveTarget && (
        <ModalPortal>
          <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50">
            <div className="cv-card w-full max-w-md p-6">
              <h2 className="font-display text-lg font-semibold mb-2">Archiver l&apos;alerte</h2>
              <p className="text-sm text-cv-muted mb-3">La preuve actuelle sera conservée avec l&apos;archivage.</p>
              <textarea
                className="cv-input w-full text-sm mb-4"
                rows={3}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Commentaire opérateur (optionnel)…"
              />
              <div className="flex gap-3 justify-end">
                <button type="button" className="cv-btn-secondary" onClick={() => setArchiveId(null)}>Annuler</button>
                <button
                  type="button"
                  className="cv-btn-primary"
                  onClick={() => {
                    const snap = archiveTarget.evidenceSnapshot
                      ?? (archiveTarget.metadata?.evidence_snapshot as Record<string, unknown> | undefined)
                      ?? {};
                    archive.mutate({ alertId: archiveId, comment, evidenceSnapshot: snap });
                    setArchiveId(null);
                  }}
                >
                  Archiver
                </button>
              </div>
            </div>
          </div>
        </ModalPortal>
      )}
    </PageShell>
  );
}
