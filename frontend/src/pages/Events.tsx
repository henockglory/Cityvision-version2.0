import { useTranslation } from 'react-i18next';
import { Clock, Camera, Circle } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import LoadingState from '@/components/ui/LoadingState';
import { useEvents } from '@/hooks/api/queries';

const typeColors: Record<string, string> = {
  motion: 'bg-amber-400',
  recording_start: 'bg-cv-accent',
  person: 'bg-blue-400',
  vehicle: 'bg-purple-400',
  connection_lost: 'bg-red-400',
};

export default function Events() {
  const { t } = useTranslation();
  const { data: events = [], isLoading } = useEvents();

  if (isLoading) return <LoadingState />;

  return (
    <div>
      <PageHeader title={t('events.title')} subtitle={t('events.timeline')} />

      <div className="cv-card p-6">
        <div className="relative">
          <div className="absolute left-[15px] top-0 bottom-0 w-px bg-cv-border" />

          <div className="space-y-6">
            {events.map((event, i) => (
              <div key={event.id} className="relative flex gap-4 pl-10 animate-slide-in" style={{ animationDelay: `${i * 50}ms` }}>
                <div className={`absolute left-2.5 top-1.5 w-2 h-2 rounded-full ${typeColors[event.type] ?? 'bg-cv-muted'}`}>
                  <Circle className="w-2 h-2" fill="currentColor" />
                </div>

                <div className="flex-1 cv-card-hover p-4 -mt-1">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="font-medium">{event.description}</p>
                      <div className="flex items-center gap-3 mt-1.5 text-xs text-cv-muted">
                        <span className="flex items-center gap-1">
                          <Camera className="w-3 h-3" />
                          {event.cameraName}
                        </span>
                        <span className="capitalize">{event.type.replace('_', ' ')}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 text-xs text-cv-muted whitespace-nowrap">
                      <Clock className="w-3 h-3" />
                      {new Date(event.timestamp).toLocaleTimeString()}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
