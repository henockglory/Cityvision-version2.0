import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  MonitorPlay, MapPin, Shapes, Radio, Trash2, MoreVertical, Wifi,
} from 'lucide-react';
import Go2RtcPlayer from '@/components/camera/Go2RtcPlayer';
import DropdownPortal from '@/components/ui/DropdownPortal';
import { go2rtcStreamSrc } from '@/config/streams';
import type { Camera } from '@/types';

interface CameraCardProps {
  camera: Camera;
  menuOpen: boolean;
  menuAnchorRef: React.RefObject<HTMLElement | null>;
  menuAnchorEl: HTMLElement | null;
  onMenuToggle: (anchor: HTMLElement | null) => void;
  onMenuClose: () => void;
  onDelete: () => void;
  onTestStream: () => void;
  testingStream?: boolean;
  statusBadge: React.ReactNode;
}

function MenuItem({
  children,
  onClick,
  to,
  danger,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  to?: string;
  danger?: boolean;
}) {
  const cls = `flex items-center gap-2.5 w-full px-3 py-2.5 text-sm transition-colors rounded-lg mx-1 ${
    danger
      ? 'text-red-400 hover:bg-red-500/10'
      : 'text-cv-text hover:bg-cv-accent/8'
  }`;
  if (to) {
    return (
      <Link to={to} className={cls} style={{ width: 'calc(100% - 0.5rem)' }} onClick={onClick}>
        {children}
      </Link>
    );
  }
  return (
    <button type="button" className={cls} onClick={onClick}>
      {children}
    </button>
  );
}

export default function CameraCard({
  camera: cam,
  menuOpen,
  menuAnchorRef,
  menuAnchorEl: _menuAnchorEl,
  onMenuToggle,
  onMenuClose,
  onDelete,
  onTestStream,
  testingStream,
  statusBadge,
}: CameraCardProps) {
  const { t } = useTranslation();
  const streamSrc = go2rtcStreamSrc(cam);

  return (
    <article className="group cv-camera-card overflow-visible">
      <div className="relative aspect-video bg-black overflow-hidden rounded-t-xl">
        <Go2RtcPlayer src={streamSrc} bare className="absolute inset-0 w-full h-full" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-black/30 pointer-events-none" />
        <div className="absolute top-3 left-3 flex items-center gap-2 pointer-events-none">
          <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-semibold uppercase tracking-wide bg-black/60 text-white border border-white/10 backdrop-blur-sm">
            <span className={`w-1.5 h-1.5 rounded-full ${cam.status !== 'offline' ? 'bg-emerald-400 animate-pulse' : 'bg-slate-400'}`} />
            {cam.status !== 'offline' ? 'Live' : 'Off'}
          </span>
        </div>
        {cam.model && (
          <span className="absolute top-3 right-3 px-2 py-0.5 rounded-md text-[10px] font-medium uppercase tracking-wider bg-cv-accent/20 text-cv-accent border border-cv-accent/30 backdrop-blur-sm pointer-events-none">
            {cam.model}
          </span>
        )}
      </div>

      <div className="p-4 border-t border-cv-border/40">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="font-display font-semibold text-cv-text truncate">{cam.name}</h3>
            <p className="flex items-center gap-1.5 text-xs text-cv-muted font-mono mt-1">
              <Wifi className="w-3 h-3 shrink-0 text-cv-accent/70" />
              {cam.ip}
            </p>
          </div>
          <div className="relative shrink-0">
            <button
              type="button"
              aria-label={t('common.actions', 'Actions')}
              className="p-2 rounded-lg text-cv-muted hover:text-cv-accent hover:bg-cv-accent/10 border border-transparent hover:border-cv-border/60 transition-all"
              onClick={(e) => {
                if (menuOpen) {
                  onMenuToggle(null);
                } else {
                  onMenuToggle(e.currentTarget);
                }
              }}
            >
              <MoreVertical className="w-4 h-4" />
            </button>
            <DropdownPortal
              anchorRef={menuAnchorRef}
              open={menuOpen && !testingStream}
              onClose={onMenuClose}
              minWidth={200}
            >
              <div className="py-1.5 px-0.5">
                <MenuItem to={`/live?camera=${cam.id}`} onClick={onMenuClose}>
                  <MonitorPlay className="w-4 h-4 text-cv-accent" />
                  Live
                </MenuItem>
                <MenuItem to="/map" onClick={onMenuClose}>
                  <MapPin className="w-4 h-4 text-cv-muted" />
                  Carte
                </MenuItem>
                <MenuItem to={`/zones?camera=${cam.id}`} onClick={onMenuClose}>
                  <Shapes className="w-4 h-4 text-cv-muted" />
                  {t('nav.zoneEditor')}
                </MenuItem>
                <MenuItem
                  onClick={() => {
                    onTestStream();
                    onMenuClose();
                  }}
                >
                  <Radio className={`w-4 h-4 ${testingStream ? 'animate-pulse text-cv-accent' : 'text-cv-muted'}`} />
                  {testingStream ? t('cameras.testingStream') : t('cameras.testStream')}
                </MenuItem>
                <div className="my-1.5 mx-2 border-t border-cv-border/50" />
                <MenuItem
                  danger
                  onClick={() => {
                    onMenuClose();
                    onDelete();
                  }}
                >
                  <Trash2 className="w-4 h-4" />
                  {t('cameras.delete')}
                </MenuItem>
              </div>
            </DropdownPortal>
          </div>
        </div>
        <div className="flex items-center justify-end mt-3 pt-3 border-t border-cv-border/30">
          {statusBadge}
        </div>
      </div>
    </article>
  );
}
