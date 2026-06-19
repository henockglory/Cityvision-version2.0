import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CheckCircle2, Loader2, Activity, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import { eventsApi } from '@/api/client';
import type { Event } from '@/types';
import { useAuthStore } from '@/stores/authStore';

interface RuleActivationFeedbackProps {
  ruleName: string;
  cameraId: string;
  cameraName?: string;
  zoneName?: string;
  lineName?: string;
  onClose: () => void;
}

const DIAGNOSTIC_DELAY_MS = 3 * 60 * 1000; // 3 minutes
const POLL_INTERVAL_MS = 10_000;            // poll every 10 s

export default function RuleActivationFeedback({
  cameraId,
  cameraName,
  zoneName,
  lineName,
  onClose,
}: RuleActivationFeedbackProps) {
  const { t } = useTranslation();
  const { orgId } = useAuthStore();
  const [eventSeen, setEventSeen] = useState(false);
  const [showDiag, setShowDiag] = useState(false);
  const activatedAt = useState(() => Date.now())[0];

  // Context label for the confirmation message
  const context = zoneName
    ? t('rules.activation.contextZone', { zoneName, cameraName: cameraName ?? cameraId })
    : lineName
    ? t('rules.activation.contextLine', { lineName, cameraName: cameraName ?? cameraId })
    : t('rules.activation.contextCamera', { cameraName: cameraName ?? cameraId });

  useEffect(() => {
    if (!orgId || eventSeen) return;

    const poll = async () => {
      try {
        const resp = await eventsApi.list(orgId, { camera_id: cameraId });
        const events: Event[] = Array.isArray(resp.data) ? resp.data : (resp as unknown as Event[]);
        const recent = events.filter((e: Event) => new Date(e.timestamp).getTime() >= activatedAt - 5000);
        if (recent.length > 0) {
          setEventSeen(true);
          return true;
        }
      } catch {
        // silent
      }
      return false;
    };

    let timer: ReturnType<typeof setInterval>;
    let diagTimer: ReturnType<typeof setTimeout>;

    const start = async () => {
      const found = await poll();
      if (found) return;

      timer = setInterval(async () => {
        const found = await poll();
        if (found) clearInterval(timer);
      }, POLL_INTERVAL_MS);

      diagTimer = setTimeout(() => {
        if (!eventSeen) setShowDiag(true);
      }, DIAGNOSTIC_DELAY_MS);
    };

    start();
    return () => {
      clearInterval(timer);
      clearTimeout(diagTimer);
    };
  }, [orgId, cameraId, activatedAt, eventSeen]);

  return (
    <div className="p-6 cv-stack-md max-w-md mx-auto">
      <div className="flex items-start gap-4">
        <CheckCircle2 className="w-6 h-6 text-metric-rules shrink-0" />
        <div className="min-w-0 space-y-1">
          <p className="font-semibold text-base leading-tight">{t('rules.activation.successTitle')}</p>
          <p className="text-sm text-cv-muted leading-relaxed">
            {t('rules.activation.successDesc', { context })}
          </p>
        </div>
      </div>

      {!eventSeen && !showDiag && (
        <div className="cv-callout text-cv-muted border border-cv-border/60 bg-cv-deep/40">
          <Loader2 className="w-4 h-4 animate-spin shrink-0" />
          <span>{t('rules.activation.watchingTitle')}</span>
        </div>
      )}

      {eventSeen && (
        <div className="cv-callout text-metric-rules border border-metric-rules/30 bg-metric-rules/5">
          <Activity className="w-4 h-4 shrink-0" />
          <span className="font-medium">{t('rules.activation.eventDetected', { defaultValue: 'Premier événement détecté !' })}</span>
        </div>
      )}

      {showDiag && !eventSeen && (
        <div className="cv-panel cv-stack-sm border-amber-400/30 bg-amber-400/5">
          <div className="flex items-center gap-2 text-amber-400">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span className="text-sm font-semibold">{t('rules.activation.noEventTitle')}</span>
          </div>
          <p className="text-xs text-cv-muted leading-relaxed">{t('rules.activation.noEventDesc')}</p>
          <ul className="cv-stack-sm text-xs text-cv-muted/90 list-none">
            <li className="flex gap-2 leading-relaxed"><span className="shrink-0">•</span>{t('rules.activation.checkZone')}</li>
            <li className="flex gap-2 leading-relaxed"><span className="shrink-0">•</span>{t('rules.activation.checkCamera')}</li>
            <li className="flex gap-2 leading-relaxed"><span className="shrink-0">•</span>{t('rules.activation.checkAi')}</li>
            <li className="flex gap-2 leading-relaxed"><span className="shrink-0">•</span>{t('rules.activation.checkActivity')}</li>
          </ul>
          <div className="flex flex-wrap gap-3 pt-1">
            <Link
              to="/system-health"
              onClick={onClose}
              className="inline-flex items-center gap-1 text-xs text-cv-accent hover:underline"
            >
              <ExternalLink className="w-3 h-3" />
              {t('rules.activation.goToHealth')}
            </Link>
            <Link
              to="/zone-editor"
              onClick={onClose}
              className="inline-flex items-center gap-1 text-xs text-cv-accent hover:underline"
            >
              <ExternalLink className="w-3 h-3" />
              {t('rules.activation.goToZones')}
            </Link>
          </div>
        </div>
      )}

      <button type="button" onClick={onClose} className="cv-btn-primary w-full text-sm py-2">
        {t('common.close', { defaultValue: 'Fermer' })}
      </button>
    </div>
  );
}
