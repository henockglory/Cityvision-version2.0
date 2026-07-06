import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { TrafficCone, Circle, Eye, Zap } from 'lucide-react';
import Modal from '@/components/ui/Modal';
import WizardSteps from '@/components/ui/WizardSteps';
import DialogTourHelpButton from '@/components/ui/DialogTourHelpButton';
import { useDialogTour } from '@/hooks/useDialogTour';

interface RedLightAssistantProps {
  open: boolean;
  onClose: () => void;
  zones: Array<{ name: string; behavior?: string }>;
  onOpenZoneEditor: (cameraId?: string) => void;
  onOpenRule: () => void;
}

export default function RedLightAssistant({
  open,
  onClose,
  zones,
  onOpenZoneEditor,
  onOpenRule,
}: RedLightAssistantProps) {
  const { t } = useTranslation();
  const [step, setStep] = useState(1);
  const hasFeu = zones.some((z) => z.behavior === 'traffic_light_color');
  const hasObs = zones.some((z) => z.behavior === 'red_light_observation');

  const prepareTourStep = useCallback((selector: string) => {
    const map: Record<string, number> = {
      '#red-light-step1': 1,
      '#red-light-step2': 2,
      '#red-light-step3': 3,
    };
    const n = map[selector];
    if (n) setStep(n);
  }, []);

  const startTour = useDialogTour('redLightAssistant', open, { prepareStep: prepareTourStep });

  const steps = [
    { n: 1, label: t('rules.redLightAssistant.step1', { defaultValue: 'Zone feu (ROI)' }), icon: Circle },
    { n: 2, label: t('rules.redLightAssistant.step2', { defaultValue: 'Zone observation' }), icon: Eye },
    { n: 3, label: t('rules.redLightAssistant.step3', { defaultValue: 'Règle + preuves' }), icon: Zap },
  ];

  return (
    <Modal
      open={open}
      onClose={onClose}
      id="red-light-assistant"
      title={t('rules.redLightAssistant.title', { defaultValue: 'Assistant feu rouge' })}
      maxWidth="md"
      footerLeft={<DialogTourHelpButton onClick={() => startTour()} />}
    >
      <div className="space-y-4">
        <p className="text-sm text-cv-muted flex items-center gap-2">
          <TrafficCone className="w-4 h-4 text-cv-accent" />
          {t('rules.redLightAssistant.intro', { defaultValue: 'Configurez les deux zones synergiques puis activez la règle feu rouge.' })}
        </p>
        <WizardSteps steps={steps} current={step} />
        {step === 1 && (
          <div id="red-light-step1" className="space-y-2 text-sm">
            <p>{t('rules.redLightAssistant.feuHint', { defaultValue: 'Dessinez une zone sur le feu avec le comportement traffic_light_color.' })}</p>
            <p className={hasFeu ? 'text-emerald-400 text-xs' : 'text-amber-400 text-xs'}>
              {hasFeu ? '✓ Zone feu détectée' : '○ Zone feu manquante'}
            </p>
            <button type="button" className="cv-btn-secondary text-sm" onClick={() => onOpenZoneEditor()}>
              {t('rules.redLightAssistant.openZoneEditor', { defaultValue: 'Ouvrir ZoneEditor' })}
            </button>
          </div>
        )}
        {step === 2 && (
          <div id="red-light-step2" className="space-y-2 text-sm">
            <p>{t('rules.redLightAssistant.obsHint', { defaultValue: 'Dessinez la zone d\'intersection (red_light_observation) sur la même caméra.' })}</p>
            <p className={hasObs ? 'text-emerald-400 text-xs' : 'text-amber-400 text-xs'}>
              {hasObs ? '✓ Zone observation détectée' : '○ Zone observation manquante'}
            </p>
            <button type="button" className="cv-btn-secondary text-sm" onClick={() => onOpenZoneEditor()}>
              {t('rules.redLightAssistant.openZoneEditor', { defaultValue: 'Ouvrir ZoneEditor' })}
            </button>
          </div>
        )}
        {step === 3 && (
          <div id="red-light-step3" className="space-y-2 text-sm">
            <p>{t('rules.redLightAssistant.ruleHint', { defaultValue: 'Activez tpl-red-light avec preuves (clip 6 s, 2 images, plaque).' })}</p>
            <button type="button" className="cv-btn-primary text-sm" disabled={!hasFeu || !hasObs} onClick={() => { onOpenRule(); onClose(); }}>
              {t('rules.redLightAssistant.activate', { defaultValue: 'Activer la règle feu rouge' })}
            </button>
            {(!hasFeu || !hasObs) && (
              <p className="text-xs text-amber-400">{t('rules.redLightAssistant.blocked', { defaultValue: 'Les deux zones sont requises avant activation.' })}</p>
            )}
          </div>
        )}
        <div className="flex justify-between pt-2">
          {step > 1 ? (
            <button type="button" className="cv-btn-secondary" onClick={() => setStep((s) => (s - 1) as 1 | 2 | 3)}>{t('common.back')}</button>
          ) : <span />}
          {step < 3 ? (
            <button type="button" className="cv-btn-primary" onClick={() => setStep((s) => (s + 1) as 1 | 2 | 3)}>{t('common.next')}</button>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}
