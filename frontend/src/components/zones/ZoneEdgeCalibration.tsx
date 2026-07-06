import { useTranslation } from 'react-i18next';

import {
  calibratedEdgeCount,
  derivedTravelDistanceM,
  edgePixelLength,
  perimeterM,
  vertexCountFromPoints,
} from '@/lib/zoneEdgeCalibration';

export default function ZoneEdgeCalibration({
  points,
  edgeDistancesM,
  onChange,
  readOnlyDistanceM,
  requiresSpeedBehavior = false,
  activeEdgeIndex = null,
  onEdgeHighlight,
  entryEdgeIndex = null,
  exitEdgeIndex = null,
  onEntryEdgeChange,
  onExitEdgeChange,
}: {
  points: number[];
  edgeDistancesM: (number | undefined)[];
  onChange: (edgeIndex: number, metres: number | undefined) => void;
  readOnlyDistanceM?: number | null;
  requiresSpeedBehavior?: boolean;
  activeEdgeIndex?: number | null;
  onEdgeHighlight?: (edgeIndex: number | null) => void;
  entryEdgeIndex?: number | null;
  exitEdgeIndex?: number | null;
  onEntryEdgeChange?: (edgeIndex: number | null) => void;
  onExitEdgeChange?: (edgeIndex: number | null) => void;
}) {
  const { t } = useTranslation();
  const n = vertexCountFromPoints(points);
  if (n < 3) return null;

  const filled = calibratedEdgeCount(edgeDistancesM);
  const derived = derivedTravelDistanceM(points, edgeDistancesM);
  const peri = perimeterM(edgeDistancesM);

  return (
    <div className="space-y-2 rounded-lg border border-cv-accent/30 bg-cv-accent/5 p-2.5">
      <p className="text-[11px] font-medium text-cv-text">{t('zoneEditor.edgeCalibrationTitle')}</p>
      {requiresSpeedBehavior && (
        <p className="text-[10px] text-amber-400/90 leading-relaxed">
          {t('zoneEditor.edgeCalibrationRequiresBehavior')}
        </p>
      )}
      <p className="text-[10px] text-cv-muted leading-relaxed">{t('zoneEditor.edgeCalibrationHint')}</p>
      {onEntryEdgeChange && onExitEdgeChange && (
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <label className="space-y-1">
            <span className="text-cv-muted">{t('zoneEditor.edgePairEntry', { defaultValue: 'Arête entrée' })}</span>
            <select
              className="cv-input w-full text-sm"
              value={entryEdgeIndex ?? ''}
              onChange={(e) => {
                const v = e.target.value === '' ? null : Number(e.target.value);
                onEntryEdgeChange(Number.isFinite(v as number) ? (v as number) : null);
              }}
            >
              <option value="">{t('zoneEditor.edgePairUnset', { defaultValue: '—' })}</option>
              {Array.from({ length: n }, (_, i) => (
                <option key={i} value={i}>{t('zoneEditor.edgeLabel', { from: i + 1, to: ((i + 1) % n) + 1 })}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-cv-muted">{t('zoneEditor.edgePairExit', { defaultValue: 'Arête sortie' })}</span>
            <select
              className="cv-input w-full text-sm"
              value={exitEdgeIndex ?? ''}
              onChange={(e) => {
                const v = e.target.value === '' ? null : Number(e.target.value);
                onExitEdgeChange(Number.isFinite(v as number) ? (v as number) : null);
              }}
            >
              <option value="">{t('zoneEditor.edgePairUnset', { defaultValue: '—' })}</option>
              {Array.from({ length: n }, (_, i) => (
                <option key={i} value={i}>{t('zoneEditor.edgeLabel', { from: i + 1, to: ((i + 1) % n) + 1 })}</option>
              ))}
            </select>
          </label>
        </div>
      )}
      <div
        className="space-y-1.5 max-h-48 overflow-y-auto pr-1"
        onMouseLeave={() => onEdgeHighlight?.(null)}
      >
        {Array.from({ length: n }, (_, i) => {
          const j = (i + 1) % n;
          const pxLen = edgePixelLength(points, i);
          const val = edgeDistancesM[i];
          const isActive = activeEdgeIndex === i;
          return (
            <div
              key={i}
              data-edge-row
              className={`flex items-center gap-2 text-[11px] rounded-md px-1.5 py-1 -mx-1.5 transition-colors ${
                isActive ? 'bg-cv-accent/15 ring-1 ring-cv-accent/50' : 'hover:bg-cv-accent/5'
              }`}
              onMouseEnter={() => onEdgeHighlight?.(i)}
            >
              <button
                type="button"
                className={`shrink-0 w-16 text-left font-medium tabular-nums ${
                  isActive ? 'text-cv-accent' : 'text-cv-muted'
                }`}
                onClick={() => onEdgeHighlight?.(i)}
              >
                {t('zoneEditor.edgeLabel', { from: i + 1, to: j + 1 })}
              </button>
              <input
                type="number"
                className="cv-input flex-1 text-sm min-w-0"
                min={0.1}
                max={5000}
                step={0.1}
                placeholder="m"
                value={val != null && val > 0 ? String(val) : ''}
                onFocus={() => onEdgeHighlight?.(i)}
                onBlur={() => {
                  requestAnimationFrame(() => {
                    if (!document.activeElement?.closest('[data-edge-row]')) {
                      onEdgeHighlight?.(null);
                    }
                  });
                }}
                onChange={(e) => {
                  const raw = e.target.value.trim();
                  if (!raw) {
                    onChange(i, undefined);
                    return;
                  }
                  const num = Number(raw);
                  onChange(i, Number.isFinite(num) && num > 0 ? num : undefined);
                }}
              />
              <span className="text-[10px] text-cv-muted/70 shrink-0 w-14 text-right">
                {(pxLen * 100).toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>
      <div className="text-[10px] text-cv-muted space-y-0.5 border-t border-cv-border/40 pt-2">
        <div>
          {t('zoneEditor.edgeCalibrationProgress', { filled, total: n })}
        </div>
        {derived != null && (
          <div>{t('zoneEditor.edgeDerivedTravel', { metres: derived.toFixed(1) })}</div>
        )}
        {peri != null && (
          <div>{t('zoneEditor.edgePerimeter', { metres: peri.toFixed(1) })}</div>
        )}
        {readOnlyDistanceM != null && readOnlyDistanceM > 0 && filled < n && (
          <div className="text-amber-400/90">{t('zoneEditor.edgeLegacyDistance', { metres: readOnlyDistanceM })}</div>
        )}
      </div>
    </div>
  );
}
