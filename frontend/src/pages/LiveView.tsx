import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ChevronUp, ChevronDown, ChevronLeft, ChevronRight,
  ZoomIn, ZoomOut, Camera, Maximize2, MonitorPlay,
} from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import VideoPlaceholder from '@/components/ui/VideoPlaceholder';
import LoadingState from '@/components/ui/LoadingState';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import { useCameras } from '@/hooks/api/queries';
import { useSound } from '@/hooks/useSound';

export default function LiveView() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const { data: cameras = [], isLoading, isError, refetch } = useCameras();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (isLoading) return <LoadingState />;

  if (isError) {
    return (
      <div>
        <PageHeader title={t('liveView.title')} />
        <ErrorState onRetry={() => void refetch()} />
      </div>
    );
  }

  if (cameras.length === 0) {
    return (
      <div>
        <PageHeader title={t('liveView.title')} />
        <EmptyState title={t('liveView.empty')} hint={t('liveView.emptyHint')} icon={MonitorPlay} />
      </div>
    );
  }

  const activeId = selectedId ?? cameras[0]?.id ?? '';
  const selected = cameras.find((c) => c.id === activeId) ?? cameras[0];

  return (
    <div>
      <PageHeader title={t('liveView.title')} />

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-3">
          <div className="cv-card overflow-hidden">
            <VideoPlaceholder label={selected.name} live={selected.status !== 'offline'} className="aspect-video rounded-none" />
            <div className="p-3 flex items-center justify-between border-t border-cv-border">
              <div>
                <p className="font-medium">{selected.name}</p>
                <p className="text-xs text-cv-muted font-mono">{selected.ip}</p>
              </div>
              <div className="flex gap-2">
                <button type="button" onClick={() => playClick()} className="cv-btn-ghost p-2">
                  <Camera className="w-4 h-4" />
                </button>
                <button type="button" onClick={() => playClick()} className="cv-btn-ghost p-2">
                  <Maximize2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="cv-card p-4">
            <h3 className="font-display text-sm font-semibold mb-3">{t('liveView.selectCamera')}</h3>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {cameras.map((cam) => (
                <button
                  key={cam.id}
                  type="button"
                  onClick={() => { playClick(); setSelectedId(cam.id); }}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                    activeId === cam.id
                      ? 'bg-cv-accent/10 text-cv-accent border border-cv-accent/20'
                      : 'hover:bg-cv-accent/5 text-cv-muted'
                  }`}
                >
                  {cam.name}
                </button>
              ))}
            </div>
          </div>

          <div className="cv-card p-4">
            <h3 className="font-display text-sm font-semibold mb-3">{t('liveView.ptz')}</h3>
            <div className="grid grid-cols-3 gap-2 max-w-[160px] mx-auto">
              <div />
              <button type="button" onClick={() => playClick()} className="cv-btn-secondary p-2 justify-center">
                <ChevronUp className="w-4 h-4" />
              </button>
              <div />
              <button type="button" onClick={() => playClick()} className="cv-btn-secondary p-2 justify-center">
                <ChevronLeft className="w-4 h-4" />
              </button>
              <div className="flex items-center justify-center">
                <div className="w-8 h-8 rounded-full border border-cv-accent/30 bg-cv-accent/10" />
              </div>
              <button type="button" onClick={() => playClick()} className="cv-btn-secondary p-2 justify-center">
                <ChevronRight className="w-4 h-4" />
              </button>
              <div />
              <button type="button" onClick={() => playClick()} className="cv-btn-secondary p-2 justify-center">
                <ChevronDown className="w-4 h-4" />
              </button>
              <div />
            </div>
            <div className="flex justify-center gap-2 mt-3">
              <button type="button" onClick={() => playClick()} className="cv-btn-ghost p-2">
                <ZoomIn className="w-4 h-4" />
              </button>
              <button type="button" onClick={() => playClick()} className="cv-btn-ghost p-2">
                <ZoomOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
