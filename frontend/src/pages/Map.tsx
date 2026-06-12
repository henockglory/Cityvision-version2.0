import { useTranslation } from 'react-i18next';
import { MapPin, Camera } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import LoadingState from '@/components/ui/LoadingState';
import { useCameras } from '@/hooks/api/queries';
import { useSound } from '@/hooks/useSound';

const mapPositions = [
  { id: 'cam-1', x: 25, y: 35 },
  { id: 'cam-2', x: 65, y: 20 },
  { id: 'cam-3', x: 45, y: 55 },
  { id: 'cam-4', x: 80, y: 70 },
  { id: 'cam-5', x: 15, y: 65 },
  { id: 'cam-6', x: 55, y: 15 },
  { id: 'cam-7', x: 35, y: 80 },
  { id: 'cam-8', x: 90, y: 40 },
];

export default function Map() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const { data: cameras = [], isLoading } = useCameras();

  if (isLoading) return <LoadingState />;

  return (
    <div>
      <PageHeader title={t('map.title')} subtitle={t('map.cameras')} />

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-3 cv-card overflow-hidden relative aspect-[16/10] min-h-[400px]">
          <div className="absolute inset-0 bg-cv-deep cv-grid-bg">
            <svg className="absolute inset-0 w-full h-full opacity-20">
              <defs>
                <pattern id="mapGrid" width="40" height="40" patternUnits="userSpaceOnUse">
                  <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#00D4FF" strokeWidth="0.5" />
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#mapGrid)" />
            </svg>

            {/* Building outline */}
            <svg className="absolute inset-0 w-full h-full" viewBox="0 0 100 100" preserveAspectRatio="none">
              <rect x="10" y="10" width="80" height="80" fill="none" stroke="#1A2D4A" strokeWidth="0.3" rx="2" />
              <rect x="30" y="30" width="25" height="20" fill="rgba(0,212,255,0.05)" stroke="#1A2D4A" strokeWidth="0.2" />
              <rect x="55" y="45" width="20" height="30" fill="rgba(0,212,255,0.05)" stroke="#1A2D4A" strokeWidth="0.2" />
            </svg>
          </div>

          {mapPositions.map((pos) => {
            const cam = cameras.find((c) => c.id === pos.id);
            if (!cam) return null;
            const isOnline = cam.status !== 'offline';
            return (
              <button
                key={pos.id}
                type="button"
                onClick={() => playClick()}
                className="absolute transform -translate-x-1/2 -translate-y-1/2 group"
                style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
              >
                <div className={`relative p-2 rounded-full border-2 transition-all group-hover:scale-110 ${
                  isOnline ? 'border-cv-accent bg-cv-accent/20 shadow-glow' : 'border-red-400/50 bg-red-400/10'
                }`}>
                  <Camera className={`w-4 h-4 ${isOnline ? 'text-cv-accent' : 'text-red-400'}`} />
                  {isOnline && (
                    <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  )}
                </div>
                <div className="absolute top-full left-1/2 -translate-x-1/2 mt-1 px-2 py-0.5 rounded bg-cv-surface border border-cv-border text-[10px] whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity">
                  {cam.name}
                </div>
              </button>
            );
          })}
        </div>

        <div className="cv-card p-4">
          <h3 className="font-display text-sm font-semibold mb-3 flex items-center gap-2">
            <MapPin className="w-4 h-4 text-cv-accent" />
            Caméras
          </h3>
          <div className="space-y-2 max-h-[500px] overflow-y-auto">
            {cameras.map((cam) => (
              <div key={cam.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-cv-accent/5 transition-colors cursor-pointer" onClick={() => playClick()}>
                <div className={`w-2 h-2 rounded-full ${cam.status !== 'offline' ? 'bg-emerald-400' : 'bg-red-400'}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{cam.name}</p>
                  <p className="text-xs text-cv-muted">{cam.location}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
