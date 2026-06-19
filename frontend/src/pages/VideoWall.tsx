import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Grid2x2, Grid3x3, LayoutGrid, Square, Grid3x3 as GridIcon, Plus } from 'lucide-react';
import PageShell from '@/components/ui/PageShell';
import VideoPlaceholder from '@/components/ui/VideoPlaceholder';
import LoadingState from '@/components/ui/LoadingState';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import { useCameras } from '@/hooks/api/queries';
import { useSound } from '@/hooks/useSound';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';
import Go2RtcPlayer from '@/components/camera/Go2RtcPlayer';
import { go2rtcStreamSrc } from '@/config/streams';

type GridSize = 1 | 4 | 9 | 16;

const layouts: { size: GridSize; icon: typeof Square; labelKey: string }[] = [
  { size: 1, icon: Square, labelKey: 'videoWall.grid1' },
  { size: 4, icon: Grid2x2, labelKey: 'videoWall.grid4' },
  { size: 9, icon: Grid3x3, labelKey: 'videoWall.grid9' },
  { size: 16, icon: LayoutGrid, labelKey: 'videoWall.grid16' },
];

function gridDimension(size: GridSize): number {
  if (size === 1) return 1;
  if (size === 4) return 2;
  if (size === 9) return 3;
  return 4;
}

export default function VideoWall() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const startTour = useAutoPageTour('videoWall');
  const [gridSize, setGridSize] = useState<GridSize>(4);
  const { data: allCameras = [], isLoading, isError, refetch } = useCameras();

  if (isLoading) return <LoadingState />;

  if (isError) {
    return (
      <PageShell title={t('videoWall.title')} onHelpTour={startTour}>
        <ErrorState onRetry={() => void refetch()} />
      </PageShell>
    );
  }

  if (allCameras.length === 0) {
    return (
      <PageShell title={t('videoWall.title')} onHelpTour={startTour}>
        <EmptyState
          title={t('videoWall.empty')}
          hint={t('videoWall.emptyHint')}
          icon={GridIcon}
          action={
            <Link to="/cameras" className="cv-btn-primary inline-flex items-center gap-2">
              <Plus className="w-4 h-4" />
              Ajouter une caméra
            </Link>
          }
        />
      </PageShell>
    );
  }

  const cameras = allCameras.slice(0, gridSize);
  const dim = gridDimension(gridSize);
  const emptySlots = Math.max(0, gridSize - cameras.length);

  const gapClass = dim >= 4 ? 'gap-1' : dim === 3 ? 'gap-1.5' : 'gap-2';

  return (
    <PageShell
      fillViewport
      title={t('videoWall.title')}
      onHelpTour={startTour}
      toolbar={
        <div
          id="video-wall-layout"
          className="flex gap-1 p-1 rounded-lg bg-cv-surface border border-cv-border w-fit"
        >
          {layouts.map((layout) => (
            <button
              key={layout.size}
              type="button"
              onClick={() => { playClick(); setGridSize(layout.size); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                gridSize === layout.size ? 'bg-cv-accent text-cv-deep' : 'text-cv-muted hover:text-cv-text'
              }`}
              title={t(layout.labelKey)}
            >
              <layout.icon className="w-4 h-4" />
              <span className="hidden sm:inline">{layout.size}</span>
            </button>
          ))}
        </div>
      }
    >
      <div
        id="video-wall-grid"
        className={`flex-1 min-h-0 w-full grid overflow-hidden ${gapClass}`}
        style={{
          gridTemplateColumns: `repeat(${dim}, minmax(0, 1fr))`,
          gridTemplateRows: `repeat(${dim}, minmax(0, 1fr))`,
        }}
      >
        {cameras.map((cam) => {
          const src = go2rtcStreamSrc(cam);
          const hasStream =
            !!cam.streamKey ||
            !!cam.streamUrl ||
            cam.metadata?.virtual === true ||
            String(cam.metadata?.source ?? '').includes('benedicte');
          return (
            <div key={cam.id} className="cv-wall-cell">
              {hasStream ? (
                <Go2RtcPlayer src={src} label={cam.name} bare />
              ) : (
                <VideoPlaceholder
                  label={cam.name}
                  live={cam.status !== 'offline'}
                  className="cv-wall-placeholder"
                />
              )}
            </div>
          );
        })}
        {Array.from({ length: emptySlots }).map((_, i) => (
          <div key={`empty-${i}`} className="cv-wall-cell cv-wall-empty" />
        ))}
      </div>
    </PageShell>
  );
}
