import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Braces, Check, ChevronsDownUp, ChevronsUpDown, Copy, Loader2 } from 'lucide-react';
import { integrationsApi, type WebhookSampleResponse } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';

type SampleKind = 'rule' | 'routing';

interface WebhookPayloadPreviewProps {
  preset: string;
  kind: SampleKind;
  /** When false, the preview stays collapsed and does not fetch. */
  active?: boolean;
  className?: string;
}

export default function WebhookPayloadPreview({
  preset,
  kind,
  active = true,
  className = '',
}: WebhookPayloadPreviewProps) {
  const { t, i18n } = useTranslation();
  const orgId = useAuthStore((s) => s.orgId);
  const [open, setOpen] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [sample, setSample] = useState<WebhookSampleResponse | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!active || !orgId || !open) return;
    let cancelled = false;
    setLoading(true);
    setError('');
    integrationsApi
      .webhookSample(orgId, { preset: preset || undefined, kind })
      .then((r) => {
        if (!cancelled) setSample(r.data);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setSample(null);
          setError((e as Error)?.message || t('integrations.webhookSample.error'));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [active, orgId, open, preset, kind, t]);

  const pretty = useMemo(() => {
    if (!sample?.body) return '';
    try {
      return JSON.stringify(sample.body, null, 2);
    } catch {
      return String(sample.body);
    }
  }, [sample]);

  const note = i18n.language.startsWith('en')
    ? sample?.note_en
    : sample?.note_fr;

  const copy = async () => {
    if (!pretty) return;
    try {
      await navigator.clipboard.writeText(pretty);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setError(t('integrations.webhookSample.copyFail'));
    }
  };

  if (!active) return null;

  return (
    <div
      className={`rounded-xl border border-cv-border/55 bg-cv-deep/20 overflow-hidden ${className}`}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left hover:bg-cv-surface/35 transition-colors"
        aria-expanded={open}
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-cv-accent/25 bg-cv-accent/10 text-cv-accent shrink-0">
          <Braces className="w-3.5 h-3.5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium text-cv-text">
            {t('integrations.webhookSample.title')}
          </span>
          <span className="block text-[11px] text-cv-muted leading-snug mt-0.5">
            {t('integrations.webhookSample.subtitle')}
          </span>
        </span>
        {open ? (
          <ChevronsDownUp className="w-4 h-4 text-cv-muted shrink-0" />
        ) : (
          <ChevronsUpDown className="w-4 h-4 text-cv-muted shrink-0" />
        )}
      </button>

      {open && (
        <div className="border-t border-cv-border/45 px-3.5 pb-3.5 pt-3 space-y-2.5">
          {note && (
            <p className="text-[11px] leading-relaxed text-cv-muted rounded-lg border border-cv-border/40 bg-cv-bg/40 px-2.5 py-2">
              {note}
            </p>
          )}

          <div className="flex items-center justify-between gap-2 flex-wrap">
            <p className="text-[10px] uppercase tracking-wide text-cv-muted font-medium">
              {sample?.cloud_events
                ? t('integrations.webhookSample.cloudEvents')
                : t('integrations.webhookSample.chatShape')}
              {preset ? ` · ${preset}` : ` · ${t('integrations.webhookSample.generic')}`}
            </p>
            <button
              type="button"
              className="cv-btn-ghost text-xs inline-flex items-center gap-1.5 px-2 py-1"
              onClick={() => void copy()}
              disabled={!pretty || loading}
              title={t('integrations.webhookSample.copy')}
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-metric-rules" />
                  {t('integrations.webhookSample.copied')}
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  {t('integrations.webhookSample.copy')}
                </>
              )}
            </button>
          </div>

          <div className="relative rounded-lg border border-cv-border/50 bg-cv-bg/70 shadow-inner">
            {loading && (
              <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-cv-bg/55 backdrop-blur-[1px]">
                <Loader2 className="w-4 h-4 animate-spin text-cv-accent" />
              </div>
            )}
            {error && !loading ? (
              <p className="px-3 py-3 text-xs text-cv-muted">{error}</p>
            ) : (
              <pre className="max-h-64 overflow-auto px-3 py-2.5 text-[11px] leading-relaxed font-mono text-cv-text whitespace-pre">
                {pretty || (loading ? '' : '{}')}
              </pre>
            )}
          </div>

          {sample?.headers_hint && sample.headers_hint.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] uppercase tracking-wide text-cv-muted font-medium">
                {t('integrations.webhookSample.headers')}
              </p>
              <ul className="rounded-lg border border-cv-border/40 bg-cv-deep/15 px-2.5 py-2 space-y-0.5">
                {sample.headers_hint.map((h) => (
                  <li key={h} className="text-[11px] font-mono text-cv-muted break-all">
                    {h}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
