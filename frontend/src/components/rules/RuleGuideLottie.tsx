import { useEffect, useState } from 'react';

/** Lottie animation by rule category with CSS fallback pulse. */
export default function RuleGuideLottie({
  category,
  className = '',
}: {
  category: string;
  className?: string;
}) {
  const [Lottie, setLottie] = useState<React.ComponentType<{
    animationData: object;
    loop?: boolean;
    autoplay?: boolean;
    className?: string;
  }> | null>(null);
  const [data, setData] = useState<object | null>(null);
  const [failed, setFailed] = useState(false);

  const slug = category.replace(/[^a-z0-9-]/gi, '') || 'behavior';

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [lottieMod, res] = await Promise.all([
          import('lottie-react'),
          fetch(`/lottie/rules/${slug}.json`),
        ]);
        if (cancelled) return;
        setLottie(() => lottieMod.default);
        if (res.ok) {
          setData((await res.json()) as object);
        } else {
          const fb = await fetch('/lottie/rules/default.json');
          if (fb.ok) setData((await fb.json()) as object);
          else setFailed(true);
        }
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (failed || !Lottie || !data) {
    return (
      <div className={`flex items-center justify-center ${className}`}>
        <div className="w-16 h-16 rounded-full border-2 border-cv-accent/40 animate-pulse flex items-center justify-center">
          <div className="w-8 h-8 rounded-full bg-cv-accent/30" />
        </div>
      </div>
    );
  }

  return (
    <div className={className}>
      <Lottie animationData={data} loop autoplay className="w-full h-full" />
    </div>
  );
}
