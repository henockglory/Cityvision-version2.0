import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronUp } from 'lucide-react';
import ZoneEditor from '@/pages/ZoneEditor';

interface DemoZoneInlinePanelProps {
  cameraId?: string;
  streamSrc?: string;
  canEdit?: boolean;
}

export default function DemoZoneInlinePanel({ cameraId, streamSrc, canEdit = false }: DemoZoneInlinePanelProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (cameraId && streamSrc && canEdit) {
      setExpanded(true);
    }
  }, [cameraId, streamSrc, canEdit]);

  if (!cameraId || !streamSrc) {
    return (
      <div id="demo-zones" className="cv-card cv-demo-zone-inline p-5">
        <div className="flex items-center gap-3">
          <div className="cv-demo-step-badge">2</div>
          <div>
            <p className="text-sm font-medium">{t('demoCenter.step2Title')}</p>
            <p className="text-xs text-cv-muted mt-0.5">{t('demoCenter.zoneInlineNeedStream')}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!canEdit) {
    return (
      <div id="demo-zones" className="cv-card cv-demo-zone-inline p-5">
        <div className="flex items-center gap-3">
          <div className="cv-demo-step-badge">2</div>
          <div>
            <p className="text-sm font-medium">{t('demoCenter.step2Title')}</p>
            <p className="text-xs text-cv-muted mt-0.5">{t('demoCenter.selectSourceBeforeZones')}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div id="demo-zones" className="cv-card cv-demo-zone-inline overflow-hidden">
      <button
        type="button"
        className="cv-demo-zone-header w-full flex items-center justify-between px-5 py-4"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="flex items-center gap-3">
          <span className="cv-demo-step-badge">2</span>
          <span className="flex flex-col items-start gap-0.5">
            <span className="text-sm font-semibold">{t('demoCenter.step2Title')}</span>
            <span className="text-[11px] text-cv-muted font-normal">{t('demoCenter.zoneInlineHint')}</span>
          </span>
        </span>
        {expanded ? <ChevronUp className="w-4 h-4 text-cv-muted shrink-0" /> : <ChevronDown className="w-4 h-4 text-cv-muted shrink-0" />}
      </button>
      {expanded && (
        <div className="px-4 pb-4 pt-0 border-t border-cv-border/60">
          <ZoneEditor embedded fixedCameraId={cameraId} fixedStreamSrc={streamSrc} />
        </div>
      )}
    </div>
  );
}
