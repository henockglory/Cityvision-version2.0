import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Check, type LucideIcon } from 'lucide-react';

const DEMO_TTL_MS = 10 * 60 * 1000;

function expiresInMinutes(timestamp: string | Date): number | null {
  const created = new Date(timestamp).getTime();
  if (Number.isNaN(created)) return null;
  const remaining = DEMO_TTL_MS - (Date.now() - created);
  if (remaining <= 0) return 0;
  return Math.ceil(remaining / 60_000);
}

export interface DemoFeedItem {
  id: string;
  primary: string;
  secondary: string;
  time: string;
  timestamp?: string;
  eventType?: string;
  isDemo?: boolean;
  acknowledged?: boolean;
  onAck?: () => void;
}

interface DemoFeedPanelProps {
  title: string;
  icon: LucideIcon;
  empty: string;
  link: string;
  items: DemoFeedItem[];
  totalCount?: number;
  maxTotal?: number;
  typeCounts?: Record<string, number>;
}

export default function DemoFeedPanel({
  title,
  icon: Icon,
  empty,
  link,
  items,
  totalCount,
  maxTotal = 20,
  typeCounts,
}: DemoFeedPanelProps) {
  const { t } = useTranslation();

  return (
    <div className="cv-card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-cv-border">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Icon className="w-4 h-4 text-cv-accent" />
          {title}
          {totalCount !== undefined ? (
            <span className="text-cv-muted font-normal">
              ({t('demoCenter.feedTotal', { count: totalCount, max: maxTotal })})
            </span>
          ) : (
            <span className="text-cv-muted font-normal">({items.length})</span>
          )}
        </div>
        <Link to={link} className="text-xs text-cv-accent hover:underline">
          {t('demoCenter.voirTout')}
        </Link>
      </div>
      {typeCounts && Object.keys(typeCounts).length > 0 && (
        <div className="px-4 py-2 flex flex-wrap gap-1.5 border-b border-cv-border/50">
          {Object.entries(typeCounts).map(([type, count]) => (
            <span key={type} className="text-[10px] px-2 py-0.5 rounded-full bg-cv-accent/10 text-cv-muted">
              {type}: {count}/20
            </span>
          ))}
        </div>
      )}
      <div className="max-h-52 overflow-y-auto divide-y divide-cv-border">
        {items.length === 0 ? (
          <p className="text-xs text-cv-muted p-4 text-center">{empty}</p>
        ) : (
          items.map((item) => {
            const mins = item.timestamp ? expiresInMinutes(item.timestamp) : null;
            return (
              <div key={item.id} className="px-4 py-2.5 flex justify-between gap-2 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate">{item.primary}</p>
                    {item.isDemo && mins !== null && (
                      <span className="text-[10px] shrink-0 px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400">
                        {t('demoCenter.testBadge', { min: mins })}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-cv-muted truncate">{item.secondary}</p>
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <span className="text-xs text-cv-muted font-mono">{item.time}</span>
                  {item.onAck && !item.acknowledged && (
                    <button
                      type="button"
                      onClick={item.onAck}
                      className="text-[10px] text-cv-accent flex items-center gap-0.5 hover:underline"
                    >
                      <Check className="w-3 h-3" /> {t('demoCenter.acquitter')}
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
