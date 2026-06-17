import { useMemo, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Bell, Camera, Workflow, Archive, Filter, ChevronRight, Film, Send } from 'lucide-react';
import PageShell from '@/components/ui/PageShell';
import SplitLayout from '@/components/ui/SplitLayout';
import SeverityBadge from '@/components/ui/SeverityBadge';
import InfoTip from '@/components/ui/InfoTip';
import EvidenceViewer from '@/components/evidence/EvidenceViewer';
import { EvidenceThumbnail } from '@/components/evidence/EvidenceMedia';
import { evidenceThumbnailUrl, parseEvidenceSnapshot } from '@/lib/evidence';
import { WEBHOOK_PRESETS } from '@/lib/evidencePolicy';
import LoadingState from '@/components/ui/LoadingState';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import ModalPortal from '@/components/ui/ModalPortal';
import { alertsApi, routingApi } from '@/api/client';
import { useAlerts, useArchiveAlert, useCameras, useRules } from '@/hooks/api/queries';
import { useAuthStore } from '@/stores/authStore';
import { useSound } from '@/hooks/useSound';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';
import type { AlertFilters } from '@/types';

export default function Alerts() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const orgId = useAuthStore((s) => s.orgId);
  const startTour = useAutoPageTour('alerts');
  const [statusFilter, setStatusFilter] = useState<'open' | 'archived' | 'all'>('open');
  const [severity, setSeverity] = useState('');
  const [cameraId, setCameraId] = useState('');
  const [ruleId, setRuleId] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [showIncomplete, setShowIncomplete] = useState(false);

  const filters: AlertFilters = useMemo(() => {
    const f: AlertFilters = { limit: 200 };
    if (statusFilter !== 'all') f.status = statusFilter;
    if (severity) f.severity = severity;
    if (cameraId) f.cameraId = cameraId;
    if (ruleId) f.ruleId = ruleId;
    if (fromDate) f.from = new Date(fromDate).toISOString();
    if (toDate) f.to = new Date(toDate).toISOString();
    if (showIncomplete) f.includeIncomplete = true;
    return f;
  }, [statusFilter, severity, cameraId, ruleId, fromDate, toDate, showIncomplete]);

  const { data: alerts = [], isLoading, isError, refetch } = useAlerts(filters);
  const { data: cameras = [] } = useCameras();
  const { data: rules = [] } = useRules();
  const archive = useArchiveAlert();
  const [archiveId, setArchiveId] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [forwardEmail, setForwardEmail] = useState('');
  const [forwardWebhook, setForwardWebhook] = useState('');
  const [forwardPreset, setForwardPreset] = useState('');
  const [forwardBusy, setForwardBusy] = useState(false);
  const [forwardMsg, setForwardMsg] = useState<string | null>(null);
  const [activeRoutingCount, setActiveRoutingCount] = useState(0);

  useEffect(() => {
    if (!orgId) return;
    void routingApi.list(orgId).then((r) => {
      setActiveRoutingCount(r.data.filter((rule) => rule.enabled).length);
    }).catch(() => undefined);
  }, [orgId]);

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
      fillViewport
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
      <div id="alerts-filters" className="cv-card p-4 flex flex-wrap gap-3 items-end shrink-0">
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
        <label className="flex items-center gap-2 text-xs text-cv-muted pb-1 cursor-pointer">
          <input type="checkbox" checked={showIncomplete} onChange={(e) => setShowIncomplete(e.target.checked)} />
          {t('events.showAll')}
        </label>
      </div>

      {activeRoutingCount > 0 && (
        <p className="text-xs text-cv-muted shrink-0">
          Routage automatique : {activeRoutingCount} règle{activeRoutingCount > 1 ? 's' : ''} active{activeRoutingCount > 1 ? 's' : ''} —{' '}
          <Link to="/settings" state={{ tab: 'routing' }} className="text-cv-accent underline">
            Paramètres → Routage
          </Link>
        </p>
      )}

      {alerts.length === 0 ? (
        <EmptyState
          title={t('alerts.empty')}
          hint={showIncomplete ? t('alerts.emptyHint') : 'Les alertes sans preuves complètes sont masquées. Cochez « Tout afficher » pour le debug.'}
          icon={Bell}
        />
      ) : (
        <div className="flex-1 min-h-0 overflow-hidden">
          <SplitLayout
            fillHeight
            className="h-full"
            listClassName="!p-0"
            list={
              <div className="relative pl-6 border-l border-cv-border/60 space-y-3 ml-2 p-2">
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
                        {(() => {
                          const thumb = evidenceThumbnailUrl(parseEvidenceSnapshot(alert.evidenceSnapshot), orgId);
                          return thumb ? (
                            <EvidenceThumbnail
                              apiUrl={thumb}
                              className="w-12 h-12 rounded object-cover shrink-0 border border-cv-border/50"
                            />
                          ) : (
                            <span className="w-12 h-12 rounded bg-cv-deep/60 border border-cv-border/40 flex items-center justify-center shrink-0">
                              <Film className="w-4 h-4 text-cv-muted" />
                            </span>
                          );
                        })()}
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
            }
            detail={selected ? (
              <div>
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
                  <EvidenceViewer evidence={selected.evidenceSnapshot} cameraId={selected.cameraId} ruleId={selected.ruleId} />
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

                {(() => {
                  const forwardLog = (selected.metadata?.forward_log ?? []) as Array<{
                    timestamp?: string;
                    source?: string;
                    channels?: string[];
                    email?: string;
                    webhook_url?: string;
                    routing_rule_name?: string;
                  }>;
                  if (forwardLog.length === 0) return null;
                  return (
                    <div className="mt-3 p-3 rounded-lg bg-cv-surface/50 border border-cv-border/60 text-xs space-y-2">
                      <p className="font-medium text-cv-text">Historique de transfert</p>
                      {forwardLog.map((entry, idx) => (
                        <div key={idx} className="flex flex-wrap gap-2 items-center border-t border-cv-border/40 pt-2 first:border-0 first:pt-0">
                          <span className={`px-2 py-0.5 rounded-full ${entry.source === 'auto_route' ? 'bg-cv-accent/10 text-cv-accent' : 'bg-cv-muted/20 text-cv-muted'}`}>
                            {entry.source === 'auto_route' ? 'Auto' : 'Manuel'}
                          </span>
                          {(entry.channels ?? []).map((ch) => (
                            <span key={ch} className="px-2 py-0.5 rounded-full bg-cv-deep/50">{ch}</span>
                          ))}
                          {entry.routing_rule_name && <span className="text-cv-muted">via {entry.routing_rule_name}</span>}
                          {entry.email && <span className="text-cv-muted">{entry.email}</span>}
                          {entry.timestamp && <span className="text-cv-muted ml-auto">{new Date(entry.timestamp).toLocaleString()}</span>}
                        </div>
                      ))}
                    </div>
                  );
                })()}

                {(() => {
                  const payload = selected.metadata?.payload as Record<string, unknown> | undefined;
                  const logs = (payload?.action_log ?? selected.metadata?.action_log) as Array<{ type?: string; status?: string }> | undefined;
                  const channels = (logs ?? [])
                    .filter((l) => l.status === 'executed')
                    .map((l) => l.type)
                    .filter(Boolean) as string[];
                  const unique = [...new Set(channels)];
                  if (unique.length === 0) return null;
                  const labels: Record<string, string> = {
                    alert: 'Alerte app',
                    notify: 'E-mail',
                    webhook: 'Webhook / automation',
                    record: 'Enregistrement',
                  };
                  return (
                    <div className="mt-3 p-3 rounded-lg bg-cv-surface/50 border border-cv-border/60 text-xs">
                      <p className="font-medium text-cv-text mb-2">{t('evidence.automationsTitle')}</p>
                      <p className="text-cv-muted mb-2">{t('evidence.automationsHint')}</p>
                      <div className="flex flex-wrap gap-2">
                        {unique.map((ch) => (
                          <span key={ch} className="px-2 py-0.5 rounded-full bg-cv-accent/10 text-cv-accent">
                            {labels[ch] ?? ch}
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })()}

                <div className="mt-4 p-4 rounded-xl border border-cv-border/60 bg-cv-deep/20 space-y-3">
                  <div className="flex items-center gap-2">
                    <Send className="w-4 h-4 text-cv-accent" />
                    <p className="font-medium text-sm">{t('evidence.forwardTitle')}</p>
                    <InfoTip content={t('evidence.forwardHint')} />
                  </div>
                  <div>
                    <label className="cv-label text-xs flex items-center gap-1">
                      {t('evidence.forwardEmail')}
                      <InfoTip content={t('evidence.forwardEmailHint')} />
                    </label>
                    <input
                      type="email"
                      className="cv-input w-full text-sm mt-1"
                      placeholder="equipe@exemple.com"
                      value={forwardEmail}
                      onChange={(e) => setForwardEmail(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="cv-label text-xs flex items-center gap-1">
                      {t('evidence.forwardPreset')}
                    </label>
                    <select
                      className="cv-input w-full text-sm mt-1"
                      value={forwardPreset}
                      onChange={(e) => setForwardPreset(e.target.value)}
                    >
                      {WEBHOOK_PRESETS.map((p) => (
                        <option key={p.id} value={p.id}>{p.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="cv-label text-xs flex items-center gap-1">
                      {t('evidence.forwardWebhook')}
                      <InfoTip content={t('evidence.forwardWebhookHint')} />
                    </label>
                    <input
                      type="url"
                      className="cv-input w-full text-sm mt-1"
                      placeholder="https://..."
                      value={forwardWebhook}
                      onChange={(e) => setForwardWebhook(e.target.value)}
                    />
                  </div>
                  {forwardMsg && (
                    <p className={`text-xs ${forwardMsg.startsWith('OK') ? 'text-metric-rules' : 'text-metric-alerts'}`}>
                      {forwardMsg}
                    </p>
                  )}
                  <button
                    type="button"
                    className="cv-btn-primary text-xs"
                    disabled={forwardBusy || (!forwardEmail && !forwardWebhook) || !orgId}
                    onClick={async () => {
                      if (!orgId || !selected) return;
                      playClick();
                      setForwardBusy(true);
                      setForwardMsg(null);
                      try {
                        await alertsApi.forward(orgId, selected.id, {
                          email: forwardEmail || undefined,
                          webhook_url: forwardWebhook || undefined,
                          webhook_preset: forwardPreset || undefined,
                        });
                        setForwardMsg(`OK — ${t('evidence.forwardSuccess')}`);
                      } catch {
                        setForwardMsg(t('evidence.forwardError'));
                      } finally {
                        setForwardBusy(false);
                      }
                    }}
                  >
                    {t('evidence.forwardSend')}
                  </button>
                </div>

                <div className="flex gap-2 mt-2">
                  {selected.cameraId && (
                    <Link to={`/live?camera=${selected.cameraId}`} className="cv-btn-ghost text-xs py-1">Voir live</Link>
                  )}
                  {selected.ruleId && (
                    <Link to="/rules" className="cv-btn-ghost text-xs py-1">Voir règles</Link>
                  )}
                </div>
              </div>
            ) : null}
          />
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
