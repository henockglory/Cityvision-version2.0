import { Video } from 'lucide-react';

interface VideoPlaceholderProps {
  label?: string;
  live?: boolean;
  className?: string;
}

export default function VideoPlaceholder({ label, live, className = '' }: VideoPlaceholderProps) {
  return (
    <div className={`cv-video-placeholder ${className}`}>
      <div className="relative z-10 flex flex-col items-center gap-2">
        <Video className="w-8 h-8 text-cv-accent/40" />
        {label && <span className="text-xs text-cv-muted font-mono">{label}</span>}
        {live && (
          <span className="cv-badge-online text-[10px]">
            LIVE
          </span>
        )}
      </div>
    </div>
  );
}
