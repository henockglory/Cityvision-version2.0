/** Fixed illustration for the rule studio guide rail (threat detection). */
export const STUDIO_GUIDE_IMAGE = '/guides/studio-guide-threat-detection.png';

/** Illustration for « Comment ça marche » blocks in the rule wizard. */
export const STUDIO_HOW_IT_WORKS_IMAGE = '/guides/studio-how-it-works.png';

/** Banner on the Rules catalog page (« Choisissez une règle adaptée à votre contexte »). */
export const RULES_CATALOG_BANNER_IMAGE = '/guides/rules-catalog-camera.png?v=2';

/** Empty state on the Rules page (« Aucune règle »). */
export const RULES_EMPTY_STATE_IMAGE = '/guides/rules-empty-eye.png?v=2';

export function ruleGuideImageSrc(_category?: string): string {
  return STUDIO_GUIDE_IMAGE;
}

export default function RuleGuideImage({
  className = '',
}: {
  category?: string;
  className?: string;
}) {
  return (
    <div className={`cv-studio-guide-image-frame w-full h-full ${className}`}>
      <img
        src={STUDIO_GUIDE_IMAGE}
        alt=""
        className="cv-studio-guide-image w-full h-full object-contain p-2"
        loading="lazy"
      />
    </div>
  );
}
