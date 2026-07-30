import { useTranslation } from 'react-i18next';
import { CheckCircle2, XCircle } from 'lucide-react';
import { useAiHealth } from '@/hooks/api/queries';

/** Env-driven integration honesty (Gemini / OCR / Frigate) — no secrets in UI. */
export default function IntegrationsStatusPanel() {
  const { t } = useTranslation();
  const { data: ai } = useAiHealth();
  const frigateLive = String(import.meta.env.VITE_FRIGATE_ENABLED || '') === '1'
    || String(import.meta.env.VITE_FRIGATE_LIVE || '') === '1';

  const rows: { label: string; ok: boolean; detail: string }[] = [
    {
      label: t('settings.geminiStatus', 'Gemini VLM / OCR'),
      ok: Boolean(ai?.geminiConfigured),
      detail: ai?.geminiConfigured
        ? (ai.geminiModel || 'gemini-3.6-flash')
        : t('settings.geminiOff', 'Désactivé — GEMINI_ENABLED + clé dans .env WSL'),
    },
    {
      label: t('settings.ocrStatus', 'OCR plaques'),
      ok: Boolean(ai?.plate) || Boolean(ai?.geminiConfigured),
      detail: ai?.geminiConfigured
        ? t('settings.ocrGemini', 'Gemini OCR (principal) — Paddle en secours si Gemini off')
        : ai?.plate
          ? t('settings.ocrOn', 'Paddle / Fast-ALPR via moteur IA')
          : t('settings.ocrOff', 'OCR non chargé — GEMINI_* ou pack ANPR'),
    },
    {
      label: t('settings.frigateStatus', 'Frigate (détection + média)'),
      ok: frigateLive || Boolean(ai?.frigateVlmBridge) || Boolean(ai?.frigateSpeedBridge),
      detail: (() => {
        const parts: string[] = [];
        if (ai?.frigateVlmBridge) {
          parts.push(t('settings.frigateVlmOn', 'VLM bridge ON — Frigate détecte · Gemini juge'));
        }
        if (ai?.frigateSpeedBridge) {
          parts.push(t('settings.frigateSpeedOn', 'Speed bridge ON — estimation Frigate vs limite CiteVision'));
        }
        if (frigateLive && parts.length === 0) {
          parts.push(t(
            'settings.frigateOn',
            'Clips / tracks / live — activer FRIGATE_VLM_BRIDGE / FRIGATE_SPEED_BRIDGE pour le métier',
          ));
        }
        if (parts.length === 0) {
          return t('settings.frigateOff', 'VITE_FRIGATE_* / bridges non activés');
        }
        return parts.join(' · ');
      })(),
    },
  ];

  return (
    <ul className="space-y-3">
      {rows.map((r) => (
        <li key={r.label} className="flex items-start gap-3 text-sm">
          {r.ok ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
          ) : (
            <XCircle className="w-4 h-4 text-cv-muted mt-0.5 shrink-0" />
          )}
          <div>
            <p className="font-medium">{r.label}</p>
            <p className="text-xs text-cv-muted">{r.detail}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}
