import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Clock, Camera, Circle, Calendar, Filter, ChevronRight, Film } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import SplitLayout from '@/components/ui/SplitLayout';
import LoadingState from '@/components/ui/LoadingState';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import EvidenceViewer from '@/components/evidence/EvidenceViewer';
import { useEvents, useCameras } from '@/hooks/api/queries';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';
import { useSound } from '@/hooks/useSound';
import { labelForEventType } from '@/lib/eventLabels';
import { evidenceThumbnailUrl, parseEvidenceSnapshot } from '@/lib/evidence';
import type { Event } from '@/types';

const typeColors: Record<string, string> = {
  running: 'bg-orange-400',
  vehicle_count_threshold: 'bg-purple-400',
  zone_enter: 'bg-orange-400',
  zone_presence: 'bg-amber-400',
  face_detected: 'bg-cyan-400',
  plate_detected: 'bg-indigo-400',
};

function EventListItem({
  evt,
  selected,
  onSelect,
}: {
  evt: Event;
  selected: boolean;
  onSelect: () => void;
}) {
  const thumb = evt.thumbnail ?? evidenceThumbnailUrl(parseEvidenceSnapshot(evt.evidenceSnapshot));
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full text-left cv-card p-3 transition-colors ${selected ? 'ring-1 ring-cv-accent/50' : 'hover:bg-cv-surface/40'}`}
    >
      <div className="flex items-start gap-2">
        {thumb ? (
          <img src={thumb} alt="" className="w-12 h-12 rounded object-cover shrink-0 border border-cv-border/50" />
        ) : (
          <span className="w-12 h-12 rounded bg-cv-deep/60 border border-cv-border/40 flex items-center justify-center shrink-0">
            <Film className="w-4 h-4 text-cv-muted" />
          </span>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Circle className={`w-2 h-2 fill-current shrink-0 ${typeColors[evt.type] ?? 'text-cv-accent'}`} />
            <p className="text-sm font-medium truncate">{evt.typeLabel ?? labelForEventType(evt.type)}</p>
          </div>
          <p className="text-xs text-cv-muted mt-1 truncate">{evt.cameraName}</p>
          <p className="text-[10px] text-cv-muted mt-0.5">{new Date(evt.timestamp).toLocaleString()}</p>
        </div>
        <ChevronRight className="w-4 h-4 text-cv-muted shrink-0" />
      </div>
    </button>
  );
}

export default function Events() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const startTour = useAutoPageTour('events');
  const { data: cameras = [] } = useCameras();
  const [eventType, setEventType] = useState('');
  const [cameraId, setCameraId] = useState('');
  const [showAll, setShowAll] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const filters = useMemo(
    () => ({
      eventType: eventType || undefined,
      cameraId: cameraId || undefined,
      showAll,
    }),
    [eventType, cameraId, showAll],
  );
  const { data: events = [], isLoading, isError, refetch } = useEvents(filters);

  const eventTypes = useMemo(() => {
    const set = new Set(events.map((e) => e.type));
    return [...set].sort();
  }, [events]);

  const selected = useMemo(
    () => events.find((e) => e.id === selectedId) ?? events[0] ?? null,
    [events, selectedId],
  );

  if (isLoading) return <LoadingState />;

  if (isError) {
    return (
      <div>
        <PageHeader title={t('events.title')} onHelpTour={startTour} />
        <ErrorState onRetry={() => void refetch()} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title={t('events.title')} subtitle={t('events.timeline')} onHelpTour={startTour} />

      <div id="events-timeline">
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <Filter className="w-4 h-4 text-cv-muted" />
          <select
            className="cv-input text-sm max-w-[180px]"
            value={eventType}
            onChange={(e) => {
              playClick();
              setEventType(e.target.value);
            }}
          >
            <option value="">{t('events.allTypes')}</option>
            {eventTypes.map((type) => (
              <option key={type} value={type}>
                {labelForEventType(type)}
              </option>
            ))}
          </select>
          <select
            className="cv-input text-sm max-w-[200px]"
            value={cameraId}
            onChange={(e) => {
              playClick();
              setCameraId(e.target.value);
            }}
          >
            <option value="">{t('events.allCameras')}</option>
            {cameras.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-xs text-cv-muted cursor-pointer">
            <input
              type="checkbox"
              checked={showAll}
              onChange={(e) => { playClick(); setShowAll(e.target.checked); }}
            />
            {t('events.showAll')}
          </label>
        </div>

        {events.length === 0 ? (
          <EmptyState title={t('events.empty')} hint={t('events.emptyHint')} icon={Calendar} />
        ) : (
          <SplitLayout
            list={(
              <div className="space-y-2 pr-1">
                {events.map((evt) => (
                  <EventListItem
                    key={evt.id}
                    evt={evt}
                    selected={selected?.id === evt.id}
                    onSelect={() => { playClick(); setSelectedId(evt.id); }}
                  />
                ))}
              </div>
            )}
            detail={selected ? (
              <div>
                <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
                  <div>
                    <span className="inline-flex items-center gap-2 text-sm font-medium">
                      <Circle className={`w-2.5 h-2.5 fill-current ${typeColors[selected.type] ?? 'text-cv-accent'}`} />
                      {selected.typeLabel ?? labelForEventType(selected.type)}
                    </span>
                    <h2 className="font-display text-lg font-semibold mt-2">{selected.description || selected.type}</h2>
                    <p className="text-xs text-cv-muted mt-1 flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {new Date(selected.timestamp).toLocaleString()}
                    </p>
                  </div>
                  {selected.confidence != null && (
                    <span className="text-xs text-cv-muted tabular-nums">
                      {Math.round(selected.confidence * 100)}%
                    </span>
                  )}
                </div>

                <div className="flex flex-wrap gap-3 text-sm text-cv-muted mb-4">
                  <span className="inline-flex items-center gap-1">
                    <Camera className="w-3.5 h-3.5" />
                    {selected.cameraName}
                  </span>
                  {selected.ruleName && (
                    <span>{selected.ruleName}</span>
                  )}
                </div>

                <div className="p-4 rounded-xl bg-cv-surface/40 border border-cv-border/60">
                  <EvidenceViewer evidence={selected.evidenceSnapshot} cameraId={selected.cameraId} />
                </div>
              </div>
            ) : (
              <p className="text-sm text-cv-muted">{t('events.selectHint')}</p>
            )}
          />
        )}
      </div>
    </div>
  );
}
