#!/usr/bin/env python3
"""
R2 - Create RuleActivationFeedback.tsx component and patch RuleActivationDialog.tsx
"""
from pathlib import Path

# ─── 1. Create the RuleActivationFeedback component ───────────────────────────
feedback_component = r'''import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CheckCircle2, Loader2, Activity, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import { eventsApi } from '@/api/client';
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
  ruleName,
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
        const events = await eventsApi.list(orgId, { cameraId, limit: 5 });
        const recent = events.filter((e: { timestamp: string }) => new Date(e.timestamp).getTime() >= activatedAt - 5000);
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
    <div className="p-5 space-y-4 max-w-md mx-auto">
      {/* Header success */}
      <div className="flex items-start gap-3">
        <CheckCircle2 className="w-6 h-6 text-metric-rules shrink-0 mt-0.5" />
        <div>
          <p className="font-semibold text-base">{t('rules.activation.successTitle')}</p>
          <p className="text-sm text-cv-muted mt-1">
            {t('rules.activation.successDesc', { context })}
          </p>
        </div>
      </div>

      {/* Live event watch status */}
      {!eventSeen && !showDiag && (
        <div className="flex items-center gap-2 text-sm text-cv-muted border border-cv-border/60 rounded-lg p-3 bg-cv-deep/40">
          <Loader2 className="w-4 h-4 animate-spin shrink-0" />
          <span>{t('rules.activation.watchingTitle')}</span>
        </div>
      )}

      {eventSeen && (
        <div className="flex items-center gap-2 text-sm text-metric-rules border border-metric-rules/30 rounded-lg p-3 bg-metric-rules/5">
          <Activity className="w-4 h-4 shrink-0" />
          <span className="font-medium">{t('rules.activation.eventDetected', { defaultValue: 'Premier événement détecté !' })}</span>
        </div>
      )}

      {/* Diagnostic panel if no event in 3 min */}
      {showDiag && !eventSeen && (
        <div className="border border-amber-400/30 rounded-lg p-3 bg-amber-400/5 space-y-2">
          <div className="flex items-center gap-2 text-amber-400">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span className="text-sm font-semibold">{t('rules.activation.noEventTitle')}</span>
          </div>
          <p className="text-xs text-cv-muted">{t('rules.activation.noEventDesc')}</p>
          <ul className="space-y-1.5 text-xs text-cv-muted/90 list-none pl-1">
            <li className="flex gap-2"><span>•</span>{t('rules.activation.checkZone')}</li>
            <li className="flex gap-2"><span>•</span>{t('rules.activation.checkCamera')}</li>
            <li className="flex gap-2"><span>•</span>{t('rules.activation.checkAi')}</li>
            <li className="flex gap-2"><span>•</span>{t('rules.activation.checkActivity')}</li>
          </ul>
          <div className="flex flex-wrap gap-2 pt-1">
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
'''

target = Path("frontend/src/components/rules/RuleActivationFeedback.tsx")
target.write_text(feedback_component, encoding="utf-8")
print(f"Created {target}")

# ─── 2. Patch RuleActivationDialog to show the feedback after save ─────────────
dialog_file = Path("frontend/src/components/rules/RuleActivationDialog.tsx")
content = dialog_file.read_text(encoding="utf-8")

if 'RuleActivationFeedback' in content:
    print("Dialog already patched")
else:
    # Add import
    OLD_IMPORT_ANCHOR = "import Go2RtcPlayer from '@/components/camera/Go2RtcPlayer';"
    NEW_IMPORT = "import Go2RtcPlayer from '@/components/camera/Go2RtcPlayer';\nimport RuleActivationFeedback from '@/components/rules/RuleActivationFeedback';"
    content = content.replace(OLD_IMPORT_ANCHOR, NEW_IMPORT)

    # Add showFeedback state after existing states near top of component
    OLD_STATE_ANCHOR = "  const [submitting, setSubmitting] = useState(false);"
    NEW_STATE = "  const [submitting, setSubmitting] = useState(false);\n  const [showFeedback, setShowFeedback] = useState(false);\n  const [feedbackCamera, setFeedbackCamera] = useState<{id:string;name:string}|null>(null);"
    content = content.replace(OLD_STATE_ANCHOR, NEW_STATE)

    # Change onActivated(); onClose(); to show feedback instead
    OLD_ACTIVATED = "      onActivated();\n      onClose();"
    NEW_ACTIVATED = """      onActivated();
      // Show post-activation feedback instead of closing immediately
      const cam = cameras.find((c) => c.id === cameraId);
      setFeedbackCamera(cam ? { id: cam.id, name: cam.name } : { id: cameraId, name: cameraId });
      setShowFeedback(true);"""
    content = content.replace(OLD_ACTIVATED, NEW_ACTIVATED)

    # Find the main return and insert the feedback overlay
    # We add it just before the closing </> or the outermost Modal
    OLD_MODAL_OPEN = "  return (\n    <Modal"
    NEW_MODAL = """  if (showFeedback && activeTemplate) {
    return (
      <Modal
        isOpen
        onClose={() => { setShowFeedback(false); onClose(); }}
        title={activeTemplate.name}
        size="sm"
      >
        <RuleActivationFeedback
          ruleName={ruleName || activeTemplate.name}
          cameraId={feedbackCamera?.id ?? cameraId}
          cameraName={feedbackCamera?.name}
          zoneName={activationCfg.zoneName}
          lineName={activationCfg.lineName}
          onClose={() => { setShowFeedback(false); onClose(); }}
        />
      </Modal>
    );
  }

  return (
    <Modal"""
    content = content.replace(OLD_MODAL_OPEN, NEW_MODAL)

    dialog_file.write_text(content, encoding="utf-8")
    print(f"Patched RuleActivationDialog.tsx")
