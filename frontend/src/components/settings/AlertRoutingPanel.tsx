import { useEffect, useState } from 'react';
import { Plus, Trash2, ToggleLeft, ToggleRight, Zap, Send, ShieldCheck, History } from 'lucide-react';
import {
  routingApi,
  integrationsApi,
  type RoutingRule,
  type DeliveryLogEntry,
} from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import { WEBHOOK_PRESETS } from '@/lib/evidencePolicy';

const MATCH_TYPES = [
  { id: 'any', label: 'Toute alerte' },
  { id: 'plate', label: 'Plaque' },
  { id: 'face', label: 'Visage' },
  { id: 'event_type', label: 'Type d\'événement' },
  { id: 'severity', label: 'Sévérité' },
] as const;

const PRESETS = [
  { name: 'Plaque → e-mail', match: { type: 'plate', value: 'ABC-123' }, channels: { emails: [''] } },
  { name: 'Critique → webhook SIEM', match: { type: 'severity', value: 'critical' }, channels: { webhook_url: '', webhook_preset: 'n8n' } },
  { name: 'Toutes alertes → e-mail', match: { type: 'any', value: '' }, channels: { emails: [''] } },
];

export default function AlertRoutingPanel() {
  const orgId = useAuthStore((s) => s.orgId);
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState('');
  const [testPlate, setTestPlate] = useState('');
  const [testResult, setTestResult] = useState<string | null>(null);
  const [signingEnabled, setSigningEnabled] = useState(false);
  const [webhookTest, setWebhookTest] = useState<Record<string, string>>({});
  const [deliveryLog, setDeliveryLog] = useState<DeliveryLogEntry[]>([]);
  const [showLog, setShowLog] = useState(false);

  const load = async () => {
    if (!orgId) return;
    setLoading(true);
    try {
      const r = await routingApi.list(orgId);
      setRules(Array.isArray(r.data) ? r.data : []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    if (orgId) {
      integrationsApi.presets(orgId).then((r) => setSigningEnabled(r.data.signing_enabled)).catch(() => {});
    }
  }, [orgId]);

  const testWebhook = async (rule: RoutingRule) => {
    if (!orgId) return;
    const channels = (rule.channels ?? {}) as Record<string, unknown>;
    const url = String(channels.webhook_url ?? '');
    if (!url) {
      setWebhookTest((p) => ({ ...p, [rule.id]: 'Renseignez d\'abord une URL.' }));
      return;
    }
    setWebhookTest((p) => ({ ...p, [rule.id]: 'Envoi…' }));
    try {
      const r = await integrationsApi.testWebhook(orgId, {
        url,
        preset: String(channels.webhook_preset ?? ''),
      });
      setWebhookTest((p) => ({ ...p, [rule.id]: r.data.ok ? '✓ Webhook livré' : `✗ ${r.data.error ?? 'échec'}` }));
    } catch (e) {
      setWebhookTest((p) => ({ ...p, [rule.id]: `✗ ${(e as Error).message}` }));
    }
  };

  const loadDeliveryLog = async () => {
    if (!orgId) return;
    setShowLog((s) => !s);
    if (!showLog) {
      try {
        const r = await integrationsApi.deliveryLog(orgId, 50);
        setDeliveryLog(r.data.entries ?? []);
      } catch { /* ignore */ }
    }
  };

  const saveRule = async (rule: RoutingRule) => {
    if (!orgId) return;
    await routingApi.update(orgId, rule.id, {
      name: rule.name,
      enabled: rule.enabled,
      priority: rule.priority,
      match: rule.match,
      channels: rule.channels,
    });
    setMsg('Règle enregistrée.');
    void load();
  };

  const addRule = async (preset?: typeof PRESETS[0]) => {
    if (!orgId) return;
    const body = preset ?? {
      name: 'Nouvelle règle',
      match: { type: 'any', value: '' },
      channels: { emails: [] },
    };
    await routingApi.create(orgId, {
      name: body.name,
      priority: (ruleList.length + 1) * 10,
      match: body.match,
      channels: body.channels,
    });
    void load();
  };

  const removeRule = async (id: string) => {
    if (!orgId) return;
    await routingApi.delete(orgId, id);
    void load();
  };

  const runTest = async () => {
    if (!orgId) return;
    const r = await routingApi.test(orgId, { plate_number: testPlate });
    setTestResult(`${r.data.count} règle(s) correspondante(s)`);
  };

  if (loading) return <p className="text-sm text-cv-muted">Chargement…</p>;

  const ruleList = rules ?? [];

  return (
    <div className="space-y-4">
      <p className="text-sm text-cv-muted">
        Les alertes sont automatiquement renvoyées selon ces règles à la création (e-mail SMTP + webhook).
        {ruleList.filter((r) => r.enabled).length > 0 && (
          <span className="block mt-1 text-cv-accent font-medium">
            {ruleList.filter((r) => r.enabled).length} règle(s) active(s)
          </span>
        )}
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-full border ${
            signingEnabled
              ? 'border-metric-rules/40 text-metric-rules bg-metric-rules/10'
              : 'border-cv-border/60 text-cv-muted bg-cv-surface/30'
          }`}
          title="Signature HMAC-SHA256 des webhooks sortants (en-tête X-CiteVision-Signature)"
        >
          <ShieldCheck className="w-3.5 h-3.5" />
          {signingEnabled ? 'Webhooks signés (HMAC)' : 'Signature webhook désactivée'}
        </span>
        <button type="button" className="cv-btn-ghost text-xs inline-flex items-center gap-1" onClick={() => void loadDeliveryLog()}>
          <History className="w-3.5 h-3.5" /> Journal de livraison
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button key={p.name} type="button" className="cv-btn-secondary text-xs" onClick={() => void addRule(p)}>
            + {p.name}
          </button>
        ))}
        <button type="button" className="cv-btn-primary text-xs" onClick={() => void addRule()}>
          <Plus className="w-3 h-3 inline" /> Nouvelle règle
        </button>
      </div>

      {ruleList.length === 0 ? (
        <p className="text-sm text-cv-muted py-4 text-center border border-dashed border-cv-border rounded-lg">
          Aucune règle de routage — ajoutez un preset ou créez une règle.
        </p>
      ) : (
        <div className="space-y-3">
          {ruleList.map((rule) => {
            const match = (rule.match ?? {}) as Record<string, string>;
            const channels = (rule.channels ?? {}) as Record<string, unknown>;
            const emails = (channels.emails as string[] | undefined) ?? (channels.email ? [String(channels.email)] : []);
            return (
              <div key={rule.id} className="p-4 rounded-xl border border-cv-border/70 bg-cv-deep/20 space-y-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <input
                    className="cv-input flex-1 min-w-[140px] text-sm font-medium"
                    value={rule.name}
                    onChange={(e) => setRules((prev) => prev.map((r) => r.id === rule.id ? { ...r, name: e.target.value } : r))}
                  />
                  <button
                    type="button"
                    className="cv-btn-ghost p-1"
                    title={rule.enabled ? 'Désactiver' : 'Activer'}
                    onClick={() => setRules((prev) => prev.map((r) => r.id === rule.id ? { ...r, enabled: !r.enabled } : r))}
                  >
                    {rule.enabled ? <ToggleRight className="w-5 h-5 text-metric-rules" /> : <ToggleLeft className="w-5 h-5 text-cv-muted" />}
                  </button>
                  <input
                    type="number"
                    className="cv-input w-16 text-xs"
                    value={rule.priority}
                    title="Priorité (plus bas = d'abord)"
                    onChange={(e) => setRules((prev) => prev.map((r) => r.id === rule.id ? { ...r, priority: Number(e.target.value) } : r))}
                  />
                  <button type="button" className="cv-btn-danger p-2" onClick={() => void removeRule(rule.id)}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
                <div className="grid sm:grid-cols-2 gap-3 text-sm">
                  <div>
                    <label className="cv-label text-xs">Si</label>
                    <select
                      className="cv-input w-full text-xs mt-1"
                      value={match.type ?? 'any'}
                      onChange={(e) => setRules((prev) => prev.map((r) => r.id === rule.id ? {
                        ...r,
                        match: { ...match, type: e.target.value },
                      } : r))}
                    >
                      {MATCH_TYPES.map((t) => (
                        <option key={t.id} value={t.id}>{t.label}</option>
                      ))}
                    </select>
                    {match.type && match.type !== 'any' && (
                      <input
                        className="cv-input w-full text-xs mt-1"
                        placeholder="Valeur (plaque, visage, type…)"
                        value={match.value ?? ''}
                        onChange={(e) => setRules((prev) => prev.map((r) => r.id === rule.id ? {
                          ...r,
                          match: { ...match, value: e.target.value },
                        } : r))}
                      />
                    )}
                  </div>
                  <div>
                    <label className="cv-label text-xs">Alors → e-mail(s)</label>
                    <input
                      className="cv-input w-full text-xs mt-1"
                      placeholder="a@ex.com, b@ex.com"
                      value={emails.join(', ')}
                      onChange={(e) => setRules((prev) => prev.map((r) => r.id === rule.id ? {
                        ...r,
                        channels: { ...channels, emails: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) },
                      } : r))}
                    />
                    <label className="cv-label text-xs mt-2 block">Webhook</label>
                    <select
                      className="cv-input w-full text-xs mt-1"
                      value={String(channels.webhook_preset ?? '')}
                      onChange={(e) => setRules((prev) => prev.map((r) => r.id === rule.id ? {
                        ...r,
                        channels: { ...channels, webhook_preset: e.target.value },
                      } : r))}
                    >
                      {WEBHOOK_PRESETS.map((p) => (
                        <option key={p.id} value={p.id}>{p.label}</option>
                      ))}
                    </select>
                    <input
                      className="cv-input w-full text-xs mt-1"
                      placeholder="https://..."
                      value={String(channels.webhook_url ?? '')}
                      onChange={(e) => setRules((prev) => prev.map((r) => r.id === rule.id ? {
                        ...r,
                        channels: { ...channels, webhook_url: e.target.value },
                      } : r))}
                    />
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <button type="button" className="cv-btn-secondary text-xs" onClick={() => void saveRule(rule)}>
                    Enregistrer
                  </button>
                  {String((channels.webhook_url ?? '')) !== '' && (
                    <button
                      type="button"
                      className="cv-btn-ghost text-xs inline-flex items-center gap-1"
                      onClick={() => void testWebhook(rule)}
                      title="Envoyer une alerte de test au webhook configuré"
                    >
                      <Send className="w-3.5 h-3.5" /> Tester le webhook
                    </button>
                  )}
                  {webhookTest[rule.id] && (
                    <span className={`text-xs ${webhookTest[rule.id].startsWith('✓') ? 'text-metric-rules' : 'text-cv-muted'}`}>
                      {webhookTest[rule.id]}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showLog && (
        <div className="p-3 rounded-lg border border-cv-border/60 bg-cv-surface/30">
          <p className="text-xs font-medium flex items-center gap-1 mb-2">
            <History className="w-3.5 h-3.5 text-cv-accent" /> Journal de livraison (50 derniers)
          </p>
          {deliveryLog.length === 0 ? (
            <p className="text-xs text-cv-muted">Aucune livraison enregistrée pour le moment.</p>
          ) : (
            <div className="space-y-1 max-h-64 overflow-auto">
              {deliveryLog.map((e, i) => (
                <div key={i} className="text-[11px] flex items-center gap-2 py-1 border-b border-cv-border/30 last:border-0">
                  <span className="text-cv-muted tabular-nums">{(e.timestamp ?? '').replace('T', ' ').slice(0, 19)}</span>
                  <span className="flex-1 truncate">{e.alert_title ?? e.alert_id}</span>
                  {(e.channels ?? []).map((c) => (
                    <span key={c} className="px-1.5 py-0.5 rounded bg-cv-deep/40 border border-cv-border/40">{c}{e.webhook_preset ? `:${e.webhook_preset}` : ''}</span>
                  ))}
                  {e.webhook_error ? <span className="text-cv-danger">✗</span> : <span className="text-metric-rules">✓</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="p-3 rounded-lg border border-cv-border/60 bg-cv-surface/30">
        <p className="text-xs font-medium flex items-center gap-1 mb-2">
          <Zap className="w-3.5 h-3.5 text-cv-accent" /> Tester (dry-run)
        </p>
        <div className="flex gap-2 flex-wrap">
          <input
            className="cv-input text-xs flex-1 min-w-[120px]"
            placeholder="Plaque test"
            value={testPlate}
            onChange={(e) => setTestPlate(e.target.value)}
          />
          <button type="button" className="cv-btn-secondary text-xs" onClick={() => void runTest()}>
            Tester
          </button>
        </div>
        {testResult && <p className="text-xs text-cv-accent mt-2">{testResult}</p>}
      </div>

      {msg && <p className="text-xs text-metric-rules">{msg}</p>}
    </div>
  );
}
