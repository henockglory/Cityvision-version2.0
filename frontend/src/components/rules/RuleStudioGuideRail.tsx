import { useEffect, useState } from 'react';

import { useTranslation } from 'react-i18next';

import type { TFunction } from 'i18next';

import { ChevronLeft, ChevronRight, BookOpen } from 'lucide-react';

import GuideIllustration from '@/components/ui/GuideIllustration';

import RuleGuideImage from '@/components/rules/RuleGuideImage';



interface RuleStudioGuideRailProps {

  templateId: string;

  category: string;

  step: 1 | 2 | 3 | 4;

  collapsed?: boolean;

  onToggleCollapse?: () => void;

}



function useGuideStep(templateId: string, step: number, t: TFunction) {

  const prefix = `rules.guides.${templateId}.step${step}`;

  const title = t(`${prefix}.title`, { defaultValue: '' });

  const body = t(`${prefix}.body`, { defaultValue: '' });

  const checklistRaw = t(`${prefix}.checklist`, { returnObjects: true, defaultValue: [] });

  const checklist = Array.isArray(checklistRaw) ? (checklistRaw as string[]) : [];

  const tipsRaw = t(`${prefix}.tips`, { returnObjects: true, defaultValue: [] });

  const tips = Array.isArray(tipsRaw) ? (tipsRaw as string[]) : [];

  const useCasesRaw = t(`rules.guides.${templateId}.useCases`, { returnObjects: true, defaultValue: [] });

  const useCases = Array.isArray(useCasesRaw)

    ? (useCasesRaw as Array<{ title?: string; body?: string }>)

    : [];



  return { title, body, checklist, tips, useCases };

}



export default function RuleStudioGuideRail({

  templateId,

  category,

  step,

  collapsed = false,

  onToggleCollapse,

}: RuleStudioGuideRailProps) {

  const { t } = useTranslation();

  const guide = useGuideStep(templateId, step, t);

  const [slide, setSlide] = useState(0);

  const [paused, setPaused] = useState(false);



  useEffect(() => {

    setSlide(0);

  }, [templateId, step]);



  useEffect(() => {

    if (guide.useCases.length <= 1 || paused) return;

    const id = window.setInterval(() => {

      setSlide((s) => (s + 1) % guide.useCases.length);

    }, 8000);

    return () => window.clearInterval(id);

  }, [guide.useCases.length, paused, templateId, step]);



  if (collapsed) {

    return (

      <button

        type="button"

        className="cv-btn-secondary w-full text-xs justify-center"

        onClick={onToggleCollapse}

      >

        <BookOpen className="w-4 h-4" />

        {t('rules.studio.guide.show')}

      </button>

    );

  }



  const hasContent = guide.title || guide.body;

  const currentCase = guide.useCases[slide];



  return (

    <aside className="rounded-xl border border-cv-accent/20 bg-gradient-to-b from-cv-accent/5 to-cv-deep/40 p-4 space-y-3 lg:sticky lg:top-0 lg:max-h-[min(70vh,520px)] lg:overflow-y-auto">

      <div className="flex items-center justify-between gap-2">

        <p className="text-xs uppercase tracking-wide text-cv-accent font-semibold flex items-center gap-1.5">

          <BookOpen className="w-3.5 h-3.5" />

          {t('rules.studio.guide.railTitle')}

        </p>

        {onToggleCollapse && (

          <button type="button" className="cv-btn-ghost text-[10px] py-0.5 px-1.5 lg:hidden" onClick={onToggleCollapse}>

            {t('rules.studio.guide.hide')}

          </button>

        )}

      </div>



      <div className="rounded-lg overflow-hidden border border-cv-border/40 bg-cv-deep/50 aspect-[4/3] max-h-44 cv-studio-guide-image-frame flex items-center justify-center">

        <RuleGuideImage category={category} className="max-h-44" />

      </div>



      {hasContent ? (

        <>

          <div>

            <p className="text-sm font-semibold text-cv-text leading-snug">{guide.title}</p>

            <p className="text-xs text-cv-muted mt-2 leading-relaxed">{guide.body}</p>

          </div>

          {guide.checklist.length > 0 && (

            <div>

              <p className="text-[11px] font-medium text-cv-text mb-1.5">{t('rules.studio.guide.checklist')}</p>

              <ol className="text-[11px] text-cv-muted list-decimal list-inside space-y-1 leading-relaxed">

                {guide.checklist.map((item, i) => (

                  <li key={i}>{item}</li>

                ))}

              </ol>

            </div>

          )}

        </>

      ) : (

        <GuideIllustration

          variant="rules"

          imageRole="guide"

          title={t('rules.studio.guide.fallbackTitle')}

          caption={t('rules.studio.guide.fallbackBody')}

          compact

          className="border-0 bg-transparent p-0"

        />

      )}



      {guide.useCases.length > 0 && (

        <div

          className="rounded-lg border border-cv-border/50 bg-cv-surface/20 p-3"

          onMouseEnter={() => setPaused(true)}

          onMouseLeave={() => setPaused(false)}

        >

          <div className="flex items-center justify-between gap-2 mb-2">

            <p className="text-[11px] font-medium text-cv-accent">{t('rules.studio.guide.useCase')}</p>

            {guide.useCases.length > 1 && (

              <div className="flex gap-1">

                <button

                  type="button"

                  className="cv-btn-ghost p-0.5"

                  onClick={() => setSlide((s) => (s - 1 + guide.useCases.length) % guide.useCases.length)}

                >

                  <ChevronLeft className="w-3.5 h-3.5" />

                </button>

                <button

                  type="button"

                  className="cv-btn-ghost p-0.5"

                  onClick={() => setSlide((s) => (s + 1) % guide.useCases.length)}

                >

                  <ChevronRight className="w-3.5 h-3.5" />

                </button>

              </div>

            )}

          </div>

          <p className="text-xs font-medium text-cv-text">{currentCase?.title}</p>

          <p className="text-[11px] text-cv-muted mt-1 leading-relaxed">{currentCase?.body}</p>

        </div>

      )}



      {guide.tips.length > 0 && (

        <ul className="text-[11px] text-cv-muted space-y-1 border-t border-cv-border/40 pt-2">

          {guide.tips.map((tip, i) => (

            <li key={i} className="flex gap-1.5">

              <span className="text-cv-accent shrink-0">→</span>

              <span>{tip}</span>

            </li>

          ))}

        </ul>

      )}

    </aside>

  );

}


