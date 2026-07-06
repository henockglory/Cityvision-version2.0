import { useTranslation } from 'react-i18next';
import { Film, Image, Target, Play } from 'lucide-react';
import InfoTip from '@/components/ui/InfoTip';
import type { EvidencePolicy } from '@/lib/evidencePolicy';
import { setEvidenceImageCount } from '@/lib/evidencePolicy';

export interface EvidencePolicyFormProps {
  policy: EvidencePolicy;
  onChange: (p: EvidencePolicy) => void;
  /** Rule studio uses i18n keys; settings panel uses plain labels when compact */
  variant?: 'studio' | 'settings';
  showEnabledToggle?: boolean;
}

export default function EvidencePolicyForm({
  policy,
  onChange,
  variant = 'studio',
  showEnabledToggle = variant === 'studio',
}: EvidencePolicyFormProps) {
  const { t } = useTranslation();
  const imageCount = policy.images.length;
  const lbl = (key: string, fallback: string) =>
    variant === 'studio' ? t(key) : fallback;

  return (
    <div className="cv-panel space-y-3">
      <div className="flex items-center gap-2">
        <Film className="w-4 h-4 text-cv-accent" />
        <h3 className="text-sm font-semibold">
          {lbl('rules.studio.evidenceTitle', 'Capture de preuves')}
        </h3>
        {variant === 'studio' && <InfoTip helpKey="evidencePolicy" content={t('rules.studio.evidenceHint')} />}
      </div>

      {showEnabledToggle && (
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={policy.enabled}
            onChange={(e) => onChange({ ...policy, enabled: e.target.checked })}
          />
          {lbl('rules.studio.evidenceEnabled', 'Activer les preuves')}
        </label>
      )}

      <div>
        <label className="cv-label flex items-center gap-1">
          {lbl('rules.studio.clipDuration', 'Durée du clip')}
          {variant === 'studio' && <InfoTip helpKey="clipDuration" content={t('rules.studio.clipDurationHint')} />}
        </label>
        <input
          type="range"
          min={3}
          max={15}
          step={1}
          value={policy.clip_seconds}
          disabled={showEnabledToggle && !policy.enabled}
          onChange={(e) => onChange({ ...policy, clip_seconds: Number(e.target.value) })}
          className="cv-range w-full"
        />
        <p className="text-xs text-cv-muted mt-1">{policy.clip_seconds} s · H.264</p>
      </div>

      <div>
        <label className="cv-label flex items-center gap-1">
          {lbl('rules.studio.imageCount', "Nombre d'images")}
          {variant === 'studio' && <InfoTip helpKey="imageCount" content={t('rules.studio.imageCountHint')} />}
        </label>
        <div className="flex gap-2 mt-1">
          {[1, 2, 3].map((n) => (
            <button
              key={n}
              type="button"
              disabled={showEnabledToggle && !policy.enabled}
              className={`flex-1 py-1.5 rounded-lg text-xs border ${
                imageCount === n
                  ? 'border-cv-accent bg-cv-accent/15 text-cv-accent'
                  : 'border-cv-border/60 text-cv-muted'
              }`}
              onClick={() => onChange(setEvidenceImageCount(policy, n))}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      {policy.images[1] && (
        <>
          <div>
            <label className="cv-label">
              {lbl('rules.studio.subjectZoom', 'Zoom sujet')}
            </label>
            <input
              type="range"
              min={1}
              max={2}
              step={0.1}
              value={policy.images[1]?.zoom ?? 1}
              disabled={showEnabledToggle && !policy.enabled}
              onChange={(e) => {
                const images = [...policy.images];
                images[1] = { ...images[1], zoom: Number(e.target.value) };
                onChange({ ...policy, images });
              }}
              className="cv-range w-full"
            />
          </div>
          <div>
            <label className="cv-label">
              {lbl('rules.studio.subjectPadding', 'Marge sujet')}
            </label>
            <input
              type="range"
              min={0}
              max={30}
              step={5}
              value={policy.images[1]?.padding_pct ?? 10}
              disabled={showEnabledToggle && !policy.enabled}
              onChange={(e) => {
                const images = [...policy.images];
                images[1] = { ...images[1], padding_pct: Number(e.target.value) };
                onChange({ ...policy, images });
              }}
              className="cv-range w-full"
            />
            <p className="text-xs text-cv-muted mt-1">{policy.images[1]?.padding_pct ?? 10} %</p>
          </div>
        </>
      )}

      <div>
        <label className="cv-label">
          {lbl('rules.studio.minConfidence', 'Confiance minimale')}
        </label>
        <input
          type="range"
          min={0}
          max={90}
          step={5}
          value={Math.round((policy.min_confidence ?? 0) * 100)}
          disabled={showEnabledToggle && !policy.enabled}
          onChange={(e) => onChange({ ...policy, min_confidence: Number(e.target.value) / 100 })}
          className="cv-range w-full"
        />
        <p className="text-xs text-cv-muted mt-1">{Math.round((policy.min_confidence ?? 0) * 100)} %</p>
      </div>

      <label className="flex items-center gap-2 text-xs text-cv-muted cursor-pointer">
        <input
          type="checkbox"
          checked={policy.draw_bbox !== false}
          disabled={showEnabledToggle && !policy.enabled}
          onChange={(e) => onChange({ ...policy, draw_bbox: e.target.checked })}
        />
        {lbl('rules.studio.drawBbox', 'Cadre de détection sur le sujet')}
      </label>

      <div className="grid grid-cols-3 gap-1 text-[10px] text-center text-cv-muted pt-1">
        <span className="p-2 rounded bg-black/20 border border-cv-border/40 flex flex-col items-center gap-1">
          <Play className="w-3 h-3" />
          Clip {policy.clip_seconds}s
        </span>
        <span className="p-2 rounded bg-black/20 border border-cv-border/40 flex flex-col items-center gap-1">
          <Image className="w-3 h-3" />
          Scène
        </span>
        <span className="p-2 rounded bg-black/20 border border-cv-border/40 flex flex-col items-center gap-1">
          <Target className="w-3 h-3" />
          {imageCount > 1 ? 'Sujet' : '—'}
        </span>
      </div>
    </div>
  );
}
