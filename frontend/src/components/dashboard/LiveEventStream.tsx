import { useEffect, useState } from 'react';
import { Activity, Pause, Play } from 'lucide-react';
import DenseEmpty from '@/components/ui/DenseEmpty';
import { useEvents } from '@/hooks/api/queries';

export default function LiveEventStream() {
  const { data: events = [], refetch, isFetching } = useEvents();
  const [live, setLive] = useState(true);

  useEffect(() => {
    if (!live) return;
    const interval = setInterval(() => void refetch(), 3000);
    return () => clearInterval(interval);
  }, [live, refetch]);

  const recent = events.slice(0, 8);

  return (
    <div id="dashboard-live" className="cv-card p-4 h-full flex flex-col">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <Activity className="w-4 h-4 text-metric-events cv-icon-spin-slow shrink-0" />
          <h2 className="font-display text-sm font-semibold truncate">Flux détections</h2>
          {live && <span className="w-2 h-2 rounded-full bg-metric-rules animate-pulse-soft shrink-0" />}
        </div>
        <button
          type="button"
          onClick={() => setLive((v) => !v)}
          className="cv-btn-ghost text-xs py-1 px-2 shrink-0"
        >
          {live ? <><Pause className="w-3 h-3" /> Pause</> : <><Play className="w-3 h-3" /> Live</>}
        </button>
      </div>
      <div className="flex-1 space-y-1.5 max-h-48 overflow-y-auto min-h-[120px]">
        {recent.length === 0 ? (
          <DenseEmpty
            title={isFetching ? 'Synchronisation…' : 'En attente d\'événements'}
            hint="Les détections IA apparaissent ici en temps réel."
          />
        ) : (
          recent.map((evt) => (
            <div
              key={evt.id}
              className="flex items-center gap-2 text-xs p-2 rounded-lg bg-cv-deep/50 border border-cv-border/60 hover:border-metric-events/30 transition-colors"
            >
              <span className="w-1.5 h-1.5 rounded-full shrink-0 bg-metric-events" />
              <span className="truncate flex-1 font-medium">{evt.typeLabel ?? evt.type}</span>
              <span className="text-cv-muted shrink-0 tabular-nums">
                {new Date(evt.timestamp).toLocaleTimeString()}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
