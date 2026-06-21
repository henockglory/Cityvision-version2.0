import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Camera, Shapes, Workflow, ArrowRight, ArrowLeft, X, CheckCircle2 } from 'lucide-react';

const STORAGE_KEY = 'cv_animated_tutorial_done';

type Step = {
  key: 'cameras' | 'zones' | 'rules';
  to: string;
  icon: typeof Camera;
  tone: string;
  illustration: JSX.Element;
};

// Lightweight animated SVG illustrations (no extra deps; pure SVG/SMIL + CSS).
const CamerasArt = (
  <svg viewBox="0 0 120 80" className="w-full h-32" role="img" aria-hidden>
    <rect x="8" y="20" width="60" height="34" rx="4" fill="rgb(var(--cv-surface))" stroke="rgb(var(--cv-border))" />
    <circle cx="38" cy="37" r="10" fill="none" stroke="rgb(var(--cv-metric-cameras))" strokeWidth="2" />
    <circle cx="38" cy="37" r="4" fill="rgb(var(--cv-metric-cameras))">
      <animate attributeName="r" values="3;5;3" dur="2s" repeatCount="indefinite" />
    </circle>
    <rect x="68" y="30" width="44" height="3" rx="1.5" fill="rgb(var(--cv-metric-cameras))" opacity="0.5">
      <animate attributeName="width" values="0;44;44" dur="2.5s" repeatCount="indefinite" />
    </rect>
    <circle cx="14" cy="26" r="2" fill="rgb(var(--cv-metric-rules))">
      <animate attributeName="opacity" values="0.3;1;0.3" dur="1.5s" repeatCount="indefinite" />
    </circle>
  </svg>
);

const ZonesArt = (
  <svg viewBox="0 0 120 80" className="w-full h-32" role="img" aria-hidden>
    <rect x="6" y="8" width="108" height="64" rx="4" fill="rgb(var(--cv-surface))" stroke="rgb(var(--cv-border))" />
    <polygon points="24,20 86,24 78,58 30,52" fill="rgb(var(--cv-accent))" fillOpacity="0.12"
      stroke="rgb(var(--cv-accent))" strokeWidth="1.5" strokeDasharray="180"
      strokeDashoffset="180">
      <animate attributeName="stroke-dashoffset" values="180;0" dur="2s" repeatCount="indefinite" />
    </polygon>
    {[[24, 20], [86, 24], [78, 58], [30, 52]].map(([x, y], i) => (
      <circle key={i} cx={x} cy={y} r="3" fill="rgb(var(--cv-accent))" />
    ))}
  </svg>
);

const RulesArt = (
  <svg viewBox="0 0 120 80" className="w-full h-32" role="img" aria-hidden>
    <rect x="10" y="32" width="28" height="16" rx="4" fill="rgb(var(--cv-metric-events))" fillOpacity="0.2" stroke="rgb(var(--cv-metric-events))" />
    <rect x="82" y="32" width="28" height="16" rx="4" fill="rgb(var(--cv-metric-rules))" fillOpacity="0.2" stroke="rgb(var(--cv-metric-rules))" />
    <line x1="38" y1="40" x2="82" y2="40" stroke="rgb(var(--cv-accent))" strokeWidth="2" strokeDasharray="6 4">
      <animate attributeName="stroke-dashoffset" values="20;0" dur="1s" repeatCount="indefinite" />
    </line>
    <circle cx="60" cy="40" r="4" fill="rgb(var(--cv-accent))">
      <animate attributeName="cx" values="40;80;40" dur="3s" repeatCount="indefinite" />
    </circle>
  </svg>
);

const STEPS: Step[] = [
  { key: 'cameras', to: '/cameras', icon: Camera, tone: 'cameras', illustration: CamerasArt },
  { key: 'zones', to: '/zones', icon: Shapes, tone: 'accent', illustration: ZonesArt },
  { key: 'rules', to: '/rules', icon: Workflow, tone: 'rules', illustration: RulesArt },
];

export default function AnimatedTutorial() {
  const { t } = useTranslation();
  const [dismissed, setDismissed] = useState(true);
  const [step, setStep] = useState(0);

  useEffect(() => {
    setDismissed(localStorage.getItem(STORAGE_KEY) === '1');
  }, []);

  // Auto-advance through the steps while visible.
  useEffect(() => {
    if (dismissed) return;
    const id = setInterval(() => setStep((s) => (s + 1) % STEPS.length), 6000);
    return () => clearInterval(id);
  }, [dismissed]);

  if (dismissed) return null;

  const finish = () => {
    localStorage.setItem(STORAGE_KEY, '1');
    setDismissed(true);
  };

  const current = STEPS[step];
  const Icon = current.icon;

  return (
    <div className="cv-card p-4 mb-5 relative overflow-hidden border-cv-accent/30">
      <button
        type="button"
        onClick={finish}
        className="absolute top-3 right-3 cv-btn-ghost p-1 text-cv-muted hover:text-cv-text"
        aria-label={t('tutorial.skip')}
      >
        <X className="w-4 h-4" />
      </button>

      <div className="flex items-center gap-2 mb-3">
        <span className="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-cv-accent/15 text-cv-accent">
          <CheckCircle2 className="w-4 h-4" />
        </span>
        <div>
          <h2 className="font-display text-sm font-semibold">{t('tutorial.title')}</h2>
          <p className="text-xs text-cv-muted">{t('tutorial.subtitle')}</p>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-4 items-center">
        <div key={current.key} className="cv-fade-in rounded-xl bg-cv-deep/40 border border-cv-border/50 p-3">
          {current.illustration}
        </div>
        <div key={`${current.key}-text`} className="cv-fade-in space-y-2">
          <div className="flex items-center gap-2">
            <Icon className={`w-5 h-5 text-metric-${current.tone === 'accent' ? 'events' : current.tone}`} />
            <span className="text-xs font-semibold uppercase tracking-wide text-cv-muted">
              {t('tutorial.stepOf', { n: step + 1, total: STEPS.length })}
            </span>
          </div>
          <h3 className="font-display text-base font-semibold">{t(`tutorial.${current.key}.title`)}</h3>
          <p className="text-sm text-cv-muted leading-relaxed">{t(`tutorial.${current.key}.desc`)}</p>
          <Link to={current.to} onClick={finish} className="cv-btn-primary text-xs inline-flex items-center gap-1">
            {t('tutorial.go')} <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      <div className="flex items-center justify-between mt-4">
        <div className="flex items-center gap-1.5">
          {STEPS.map((s, i) => (
            <button
              key={s.key}
              type="button"
              onClick={() => setStep(i)}
              aria-label={`step ${i + 1}`}
              className={`h-1.5 rounded-full transition-all ${i === step ? 'w-6 bg-cv-accent' : 'w-1.5 bg-cv-border'}`}
            />
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="cv-btn-ghost text-xs inline-flex items-center gap-1 disabled:opacity-40"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0}
          >
            <ArrowLeft className="w-3.5 h-3.5" /> {t('tutorial.prev')}
          </button>
          {step < STEPS.length - 1 ? (
            <button type="button" className="cv-btn-secondary text-xs inline-flex items-center gap-1" onClick={() => setStep((s) => s + 1)}>
              {t('tutorial.next')} <ArrowRight className="w-3.5 h-3.5" />
            </button>
          ) : (
            <button type="button" className="cv-btn-secondary text-xs" onClick={finish}>
              {t('tutorial.done')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
