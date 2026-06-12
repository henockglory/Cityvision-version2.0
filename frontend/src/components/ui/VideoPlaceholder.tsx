import { Camera, Radio } from 'lucide-react';

interface VideoPlaceholderProps {
  label?: string;
  live?: boolean;
  className?: string;
}

export default function VideoPlaceholder({ label, live = true, className = '' }: VideoPlaceholderProps) {
  return (
    <div className={`cv-video-placeholder ${className}`}>
      <div className="relative z-10 flex flex-col items-center gap-2 text-cv-muted">
        <Camera className="w-8 h-8 opacity-40" />
        {label && <span className="text-xs font-medium">{label}</span>}
      </div>
      {live && (
        <div className="absolute top-2 left-2 z-10 flex items-center gap-1.5 px-2 py-0.5 rounded bg-red-500/20 border border-red-500/40">
          <Radio className="w-3 h-3 text-red-400 animate-pulse" />
          <span className="text-[10px] font-medium text-red-400 uppercase tracking-wider">Live</span>
        </div>
      )}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cv-accent/50 to-transparent" />
    </div>
  );
}
