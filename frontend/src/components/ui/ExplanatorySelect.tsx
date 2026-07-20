import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Search } from 'lucide-react';
import DropdownPortal from '@/components/ui/DropdownPortal';
import { useModalLayerZIndex } from '@/components/ui/ModalLayerContext';
import { LAYER } from '@/lib/layerZIndex';

export interface ExplanatoryOption {
  value: string;
  label: string;
  technicalId: string;
  technology: string;
  howItWorks: string;
  stepUtility: string;
  group?: string;
  disabled?: boolean;
  disabledReason?: string;
}

export interface ExplanatorySelectProps {
  value: string;
  onChange: (value: string) => void;
  options: ExplanatoryOption[];
  placeholder?: string;
  className?: string;
  compact?: boolean;
  searchable?: boolean;
  disabled?: boolean;
  zIndex?: number;
  emptyLabel?: string;
}

function formatDescription(opt: ExplanatoryOption): string {
  return `${opt.technology} | ${opt.howItWorks} | ${opt.stepUtility}`;
}

export default function ExplanatorySelect({
  value,
  onChange,
  options,
  placeholder = '— Choisir —',
  className = '',
  compact = false,
  searchable,
  disabled = false,
  zIndex: zIndexProp,
  emptyLabel,
}: ExplanatorySelectProps) {
  const modalLayerZ = useModalLayerZIndex();
  const zIndex = zIndexProp ?? modalLayerZ ?? LAYER.dropdown;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [highlight, setHighlight] = useState(0);
  const listId = useId();

  const showSearch = searchable ?? options.length > 8;
  const selected = options.find((o) => o.value === value);

  const filtered = useMemo(() => {
    if (!query.trim()) return options;
    const q = query.toLowerCase();
    return options.filter(
      (o) =>
        o.label.toLowerCase().includes(q) ||
        o.technicalId.toLowerCase().includes(q) ||
        o.technology.toLowerCase().includes(q) ||
        o.howItWorks.toLowerCase().includes(q) ||
        o.stepUtility.toLowerCase().includes(q),
    );
  }, [options, query]);

  const grouped = useMemo(() => {
    const map = new Map<string, ExplanatoryOption[]>();
    for (const opt of filtered) {
      const g = opt.group ?? '';
      if (!map.has(g)) map.set(g, []);
      map.get(g)!.push(opt);
    }
    return map;
  }, [filtered]);

  const flatFiltered = useMemo(() => filtered, [filtered]);

  const close = useCallback(() => {
    setOpen(false);
    setQuery('');
  }, []);

  const select = useCallback(
    (v: string) => {
      const opt = options.find((o) => o.value === v);
      if (opt?.disabled) return;
      onChange(v);
      close();
    },
    [onChange, close, options],
  );

  useEffect(() => {
    if (!open) return;
    setHighlight(0);
  }, [open, query]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        close();
        return;
      }
      if (!open) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setHighlight((h) => Math.min(h + 1, flatFiltered.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setHighlight((h) => Math.max(h - 1, 0));
      } else if (e.key === 'Enter' && flatFiltered[highlight]) {
        e.preventDefault();
        select(flatFiltered[highlight].value);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, flatFiltered, highlight, select, close]);

  useEffect(() => {
    if (!open || !listRef.current) return;
    const el = listRef.current.querySelector(`[data-idx="${highlight}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [highlight, open]);

  let itemIdx = -1;

  return (
    <div className={`relative min-w-0 ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        className={`cv-explanatory-select-trigger w-full text-left ${compact ? 'cv-explanatory-select-trigger-compact' : ''} ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        onClick={() => !disabled && setOpen((o) => !o)}
      >
        <span className="flex-1 min-w-0">
          {selected ? (
            <>
              <span className={`block truncate ${compact ? 'text-xs' : 'text-sm'} text-cv-text font-medium`}>
                {selected.label}{' '}
                <span className="text-cv-muted font-normal">({selected.technicalId})</span>
              </span>
              {!compact && (
                <span className="block text-[10px] text-cv-muted/80 truncate mt-0.5">
                  {formatDescription(selected)}
                </span>
              )}
            </>
          ) : (
            <span className={`${compact ? 'text-xs' : 'text-sm'} text-cv-muted`}>{placeholder}</span>
          )}
        </span>
        <ChevronDown className={`w-4 h-4 shrink-0 text-cv-muted transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      <DropdownPortal
        anchorRef={triggerRef}
        open={open}
        onClose={close}
        minWidth={compact ? 320 : 420}
        zIndex={zIndex}
        align="left"
      >
        <div id={listId} role="listbox" className="cv-explanatory-select-panel">
          {showSearch && (
            <div className="sticky top-0 z-10 p-2 border-b border-cv-border/50 bg-cv-surface/98 backdrop-blur-md">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-cv-muted" />
                <input
                  type="search"
                  className="cv-input text-xs py-1.5 pl-8 pr-2"
                  placeholder="Rechercher…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  autoFocus
                />
              </div>
            </div>
          )}
          <div ref={listRef} className="max-h-72 overflow-y-auto py-1">
            {flatFiltered.length === 0 && (
              <p className="px-3 py-4 text-xs text-cv-muted text-center">{emptyLabel ?? 'Aucun résultat'}</p>
            )}
            {Array.from(grouped.entries()).map(([group, items]) => (
              <div key={group || '__default'}>
                {group && (
                  <p className="cv-explanatory-option-group sticky top-0 z-[1] px-3 py-1.5 text-[10px] uppercase tracking-wide font-semibold text-cv-accent bg-cv-surface/95 backdrop-blur-sm border-b border-cv-border/30">
                    {group}
                  </p>
                )}
                {items.map((opt) => {
                  itemIdx += 1;
                  const idx = itemIdx;
                  const isSelected = opt.value === value;
                  const isHighlight = idx === highlight;
                  const isDisabled = Boolean(opt.disabled);
                  return (
                    <button
                      key={`${opt.group ?? ''}-${opt.value}`}
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      aria-disabled={isDisabled}
                      data-idx={idx}
                      disabled={isDisabled}
                      className={`cv-explanatory-option w-full text-left ${isSelected ? 'cv-explanatory-option-selected' : ''} ${isHighlight ? 'cv-explanatory-option-highlight' : ''} ${isDisabled ? 'opacity-45 cursor-not-allowed' : ''}`}
                      onMouseEnter={() => !isDisabled && setHighlight(idx)}
                      onClick={() => !isDisabled && select(opt.value)}
                    >
                      <div className="flex items-start gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-cv-text leading-snug">
                            {opt.label}{' '}
                            <span className="text-cv-muted font-normal text-xs">({opt.technicalId})</span>
                          </p>
                          <p className="text-[11px] text-cv-muted/90 mt-1 leading-relaxed">
                            {isDisabled && opt.disabledReason
                              ? opt.disabledReason
                              : formatDescription(opt)}
                          </p>
                        </div>
                        {isSelected && <Check className="w-4 h-4 shrink-0 text-cv-accent mt-0.5" />}
                      </div>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </DropdownPortal>
    </div>
  );
}

export function metaToOption(meta: {
  label: string;
  technicalId: string;
  technology: string;
  howItWorks: string;
  stepUtility: string;
  group?: string;
}, value?: string): ExplanatoryOption {
  const id = value ?? meta.technicalId;
  return { value: id, ...meta, technicalId: meta.technicalId || id };
}
