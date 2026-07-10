import { useEffect, useState } from 'react';

import { useTranslation } from 'react-i18next';

import type { OverlayTrack } from '@/lib/detectionTrackState';

import { classLabel } from '@/lib/detectionClasses';

import { paletteForClass } from '@/lib/detectionOverlayStyle';

import { computeContainedRect } from '@/lib/videoLayout';



interface LiveDetectionOverlayProps {

  containerRef: React.RefObject<HTMLDivElement | null>;

  tracks: OverlayTrack[];

  resolution: { width: number; height: number } | null;

  stale?: boolean;

}



export default function LiveDetectionOverlay({

  containerRef,

  tracks,

  resolution,

  stale = false,

}: LiveDetectionOverlayProps) {

  const { i18n } = useTranslation();

  const lang = i18n.language.startsWith('en') ? 'en' : 'fr';

  const [layout, setLayout] = useState({ cw: 0, ch: 0, vw: 1920, vh: 1080 });



  useEffect(() => {

    const el = containerRef.current;

    if (!el) return;

    const ro = new ResizeObserver(([entry]) => {

      const { width, height } = entry.contentRect;

      const res = resolution;

      setLayout({

        cw: width,

        ch: height,

        vw: res?.width ?? 1920,

        vh: res?.height ?? 1080,

      });

    });

    ro.observe(el);

    return () => ro.disconnect();

  }, [containerRef, resolution?.width, resolution?.height]);



  if (layout.cw <= 0 || tracks.length === 0) return null;



  const rect = computeContainedRect(layout.cw, layout.ch, layout.vw, layout.vh);

  const baseOpacity = stale ? 0.4 : 1;



  return (

    <div className="absolute inset-0 pointer-events-none z-10" aria-hidden>

      <div

        className="absolute"

        style={{ left: rect.left, top: rect.top, width: rect.width, height: rect.height }}

      >

        {tracks.map((d) => {

          const pal = paletteForClass(d.class_name);

          const label = classLabel(d.class_name, lang);

          const pct = (v: number) => `${Math.min(100, Math.max(0, v * 100))}%`;

          const opacity = baseOpacity * d.opacity;

          return (

            <div

              key={d.track_id}

              className="absolute box-border rounded-sm"

              style={{

                left: pct(d.bbox.x),

                top: pct(d.bbox.y),

                width: pct(d.bbox.width),

                height: pct(d.bbox.height),

                border: `2px solid ${pal.border}`,

                backgroundColor: pal.fill,

                boxShadow: `0 0 12px ${pal.border}55, inset 0 0 0 1px rgba(255,255,255,0.08)`,

                opacity,

                transition: 'opacity 0.12s ease',

              }}

            >

              <span

                className="absolute -top-5 left-0 max-w-[140px] truncate px-1.5 py-0.5 rounded text-[10px] font-semibold tracking-wide shadow-md"

                style={{

                  backgroundColor: 'rgba(8, 12, 20, 0.82)',

                  color: pal.label,

                  border: `1px solid ${pal.border}88`,

                }}

              >

                {label}

                <span className="opacity-70 font-mono ml-1">

                  {Math.round(d.confidence * 100)}%

                </span>

              </span>

            </div>

          );

        })}

      </div>

    </div>

  );

}


