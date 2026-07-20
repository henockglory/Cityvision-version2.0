import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Send } from 'lucide-react';
import InfoTip from '@/components/ui/InfoTip';
import ExplanatorySelect from '@/components/ui/ExplanatorySelect';
import { buildWebhookPresetOptions } from '@/lib/conditionValueOptions';
import { WEBHOOK_PRESETS } from '@/lib/evidencePolicy';

interface OutputChannelsPanelProps {
  notifyEmail: string;
  onNotifyEmail: (v: string) => void;
  webhookPreset: string;
  onWebhookPreset: (v: string) => void;
  webhookUrl: string;
  onWebhookUrl: (v: string) => void;
  enableWebhook: boolean;
  onEnableWebhook: (v: boolean) => void;
}

export default function OutputChannelsPanel({
  notifyEmail,
  onNotifyEmail,
  webhookPreset,
  onWebhookPreset,
  webhookUrl,
  onWebhookUrl,
  enableWebhook,
  onEnableWebhook,
}: OutputChannelsPanelProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.startsWith('en') ? 'en' : 'fr';
  const webhookOptions = useMemo(() => buildWebhookPresetOptions(WEBHOOK_PRESETS, lang), [lang]);

  return (
    <div className="space-y-3 p-4 rounded-xl border border-cv-border/60 bg-cv-deep/30">
      <div className="flex items-center gap-2">
        <Send className="w-4 h-4 text-cv-accent" />
        <h3 className="text-sm font-semibold">{t('rules.studio.outputsTitle')}</h3>
        <InfoTip helpKey="outputChannels" content={t('rules.studio.outputsHint')} />
      </div>

      <div>
        <label className="cv-label flex items-center gap-1">
          {t('rules.studio.notifyEmail')}
          <InfoTip helpKey="notifyEmail" content={t('rules.studio.notifyEmailHint')} />
        </label>
        <input
          type="email"
          className="cv-input w-full"
          placeholder="equipe.securite@exemple.com"
          value={notifyEmail}
          onChange={(e) => onNotifyEmail(e.target.value)}
        />
      </div>

      <label className="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox" checked={enableWebhook} onChange={(e) => onEnableWebhook(e.target.checked)} />
        {t('rules.studio.enableWebhook')}
      </label>

      {enableWebhook && (
        <>
          <div>
            <label className="cv-label">{t('rules.studio.webhookPreset')}</label>
            <ExplanatorySelect
              className="w-full"
              value={webhookPreset}
              onChange={onWebhookPreset}
              options={webhookOptions}
              searchable={false}
            />
          </div>
          {webhookPreset !== 'gmail' && (
            <div>
              <label className="cv-label">{t('rules.studio.webhookUrl')}</label>
              <input
                type="url"
                className="cv-input w-full"
                placeholder="https://..."
                value={webhookUrl}
                onChange={(e) => onWebhookUrl(e.target.value)}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
