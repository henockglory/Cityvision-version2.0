import { useRef, useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import DropdownPortal from '@/components/ui/DropdownPortal';

export interface PremiumSelectOption {
  value: string;
  label: string;
}

interface PremiumSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: PremiumSelectOption[];
  placeholder?: string;
  className?: string;
  triggerClassName?: string;
  minWidth?: number;
  zIndex?: number;
}

/** Premium combobox matching the app theme — replaces native <select>. */
export default function PremiumSelect({
  value,
  onChange,
  options,
  placeholder = '—',
  className = '',
  triggerClassName = '',
  minWidth = 220,
  zIndex = 200,
}: PremiumSelectProps) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => o.value === value);

  return (
    <div className={`relative ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        className={`cv-input text-sm flex items-center justify-between gap-2 w-full cursor-pointer ${triggerClassName}`}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="text-left flex-1 whitespace-normal leading-snug">
          {selected?.label ?? placeholder}
        </span>
        <ChevronDown className={`w-4 h-4 text-cv-muted shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      <DropdownPortal anchorRef={triggerRef} open={open} onClose={() => setOpen(false)} minWidth={minWidth} zIndex={zIndex}>
        <div className="cv-explanatory-select-panel py-1">
          {options.map((opt) => {
            const isSelected = opt.value === value;
            return (
              <button
                key={opt.value || '__empty'}
                type="button"
                role="option"
                aria-selected={isSelected}
                className={`cv-explanatory-option w-full text-left ${isSelected ? 'cv-explanatory-option-selected' : ''}`}
                onClick={() => { onChange(opt.value); setOpen(false); }}
              >
                <div className="flex items-start gap-2">
                  <span className="flex-1 text-sm leading-snug">{opt.label}</span>
                  {isSelected && <Check className="w-4 h-4 shrink-0 text-cv-accent mt-0.5" />}
                </div>
              </button>
            );
          })}
        </div>
      </DropdownPortal>
    </div>
  );
}
