import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Grid2x2, Grid3x3, LayoutGrid, Square } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import VideoPlaceholder from '@/components/ui/VideoPlaceholder';
import LoadingState from '@/components/ui/LoadingState';
import { useCameras } from '@/hooks/api/queries';
import { useSound } from '@/hooks/useSound';

type GridSize = 1 | 4 | 9 | 16;

const layouts: { size: GridSize; icon: typeof Square; labelKey: string }[] = [
  { size: 1, icon: Square, labelKey: 'videoWall.grid1' },
  { size: 4, icon: Grid2x2, labelKey: 'videoWall.grid4' },
  { size: 9, icon: Grid3x3, labelKey: 'videoWall.grid9' },
  { size: 16, icon: LayoutGrid, labelKey: 'videoWall.grid16' },
];

const gridCols: Record<GridSize, string> = {
  1: 'grid-cols-1',
  4: 'grid-cols-2',
  9: 'grid-cols-3',
  16: 'grid-cols-4',
};

export default function VideoWall() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const [gridSize, setGridSize] = useState<GridSize>(4);
  const { data: allCameras = [], isLoading } = useCameras();

  if (isLoading) return <LoadingState />;

  const cameras = allCameras.slice(0, gridSize);

  return (
    <div>
      <PageHeader
        title={t('videoWall.title')}
        actions={
          <div className="flex gap-1 p-1 rounded-lg bg-cv-surface border border-cv-border">
            {layouts.map((layout) => (
              <button
                key={layout.size}
                type="button"
                onClick={() => { playClick(); setGridSize(layout.size); }}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  gridSize === layout.size ? 'bg-cv-accent text-cv-deep' : 'text-cv-muted hover:text-[var(--cv-text)]'
                }`}
                title={t(layout.labelKey)}
              >
                <layout.icon className="w-4 h-4" />
                <span className="hidden sm:inline">{layout.size}</span>
              </button>
            ))}
          </div>
        }
      />

      <div className={`grid ${gridCols[gridSize]} gap-2`}>
        {cameras.map((cam) => (
          <VideoPlaceholder
            key={cam.id}
            label={cam.name}
            live={cam.status !== 'offline'}
            className={gridSize === 1 ? 'aspect-video' : 'aspect-video'}
          />
        ))}
        {Array.from({ length: Math.max(0, gridSize - cameras.length) }).map((_, i) => (
          <div key={`empty-${i}`} className="cv-video-placeholder aspect-video opacity-30" />
        ))}
      </div>
    </div>
  );
}
