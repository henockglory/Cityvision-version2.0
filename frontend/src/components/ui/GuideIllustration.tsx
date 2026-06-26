import {
  RULES_CATALOG_BANNER_IMAGE,
  RULES_EMPTY_STATE_IMAGE,
  STUDIO_GUIDE_IMAGE,
  STUDIO_HOW_IT_WORKS_IMAGE,
} from '@/components/rules/RuleGuideImage';

interface GuideIllustrationProps {
  title: string;
  caption: string;
  variant?: 'rules' | 'spatial' | 'alerts' | 'live' | 'road-enforcement' | 'crowd' | 'identity' | 'composite' | 'incident' | 'default';
  src?: string;
  /** guide = rail Guide; howItWorks = « Comment ça marche »; catalog = bannière page Règles; empty = état vide */
  imageRole?: 'guide' | 'howItWorks' | 'catalog' | 'empty';
  compact?: boolean;
  className?: string;
}

const VARIANT_ACCENT: Record<string, string> = {
  rules: '#10b981',
  spatial: '#8b5cf6',
  alerts: '#f59e0b',
  live: '#3b82f6',
  'road-enforcement': '#ef4444',
  crowd: '#8b5cf6',
  identity: '#06b6d4',
  composite: '#f59e0b',
  incident: '#f59e0b',
  default: '#3b82f6',
};

function resolveImageSrc(
  imageRole: GuideIllustrationProps['imageRole'],
  src?: string,
): string | undefined {
  if (src) return src;
  if (imageRole === 'guide') return STUDIO_GUIDE_IMAGE;
  if (imageRole === 'howItWorks') return STUDIO_HOW_IT_WORKS_IMAGE;
  if (imageRole === 'catalog') return RULES_CATALOG_BANNER_IMAGE;
  if (imageRole === 'empty') return RULES_EMPTY_STATE_IMAGE;
  return undefined;
}

export default function GuideIllustration({
  title,
  caption,
  variant = 'default',
  src,
  imageRole,
  compact = false,
  className = '',
}: GuideIllustrationProps) {
  const accent = VARIANT_ACCENT[variant] ?? VARIANT_ACCENT.default;
  const imageSrc = resolveImageSrc(imageRole, src);
  const frameSize = compact ? 'w-20 h-20' : imageRole === 'empty' ? 'w-32 h-32' : 'w-28 h-28';
  const usesTransparentPng = imageRole === 'catalog' || imageRole === 'guide' || imageRole === 'empty';
  const imageFrameClass =
    imageRole === 'howItWorks'
      ? `${frameSize} bg-white/95`
      : usesTransparentPng
        ? `${frameSize} bg-transparent`
        : `${frameSize} bg-cv-deep/60`;

  return (
    <div
      className={`flex gap-4 items-center rounded-xl border border-cv-border/60 bg-cv-deep/30 ${
        compact ? 'p-3' : 'p-4'
      } ${className}`}
    >
      {imageSrc ? (
        <div
          className={`cv-studio-guide-image-frame shrink-0 rounded-lg ${imageFrameClass}`}
        >
          <img
            src={imageSrc}
            alt=""
            className={`cv-studio-guide-image w-full h-full motion-safe:animate-fade-in object-contain ${
              usesTransparentPng ? 'p-0' : imageRole === 'howItWorks' ? 'p-1' : 'p-1.5'
            }`}
          />
        </div>
      ) : (
        <svg
          viewBox="0 0 120 80"
          className={`shrink-0 motion-safe:animate-fade-in ${compact ? 'w-20 h-14' : 'w-28 h-20'}`}
          aria-hidden
        >
          <rect x="8" y="12" width="64" height="48" rx="6" fill="none" stroke={accent} strokeWidth="2" opacity="0.7" />
          <circle cx="40" cy="36" r="10" fill="none" stroke={accent} strokeWidth="1.5" strokeDasharray="4 3" />
          <path d="M88 20 L108 36 L88 52 Z" fill={accent} opacity="0.25" stroke={accent} strokeWidth="1.5" />
          <line x1="98" y1="36" x2="108" y2="36" stroke={accent} strokeWidth="2" />
        </svg>
      )}
      <div className="min-w-0">
        <p className={`font-medium text-cv-text ${compact ? 'text-xs' : 'text-sm'}`}>{title}</p>
        <p className={`text-cv-muted mt-1 leading-relaxed ${compact ? 'text-[11px] line-clamp-2' : 'text-xs'}`}>
          {caption}
        </p>
      </div>
    </div>
  );
}
