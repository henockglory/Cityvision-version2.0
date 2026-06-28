interface SegmentedTab {
  id: string;
  label: string;
}

interface SegmentedTabsProps {
  tabs?: SegmentedTab[];
  /** @deprecated use tabs with { id, label } */
  options?: { value: string; label: string }[];
  value: string;
  onChange: (id: string) => void;
  className?: string;
}

export default function SegmentedTabs({
  tabs,
  options,
  value,
  onChange,
  className = '',
}: SegmentedTabsProps) {
  const items: SegmentedTab[] = tabs ?? options?.map((o) => ({ id: o.value, label: o.label })) ?? [];
  return (
    <div
      className={`flex p-1 rounded-lg bg-cv-deep/50 border border-cv-border/60 gap-1 ${className}`}
      role="tablist"
    >
      {items.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={value === tab.id}
          className={`flex-1 sm:flex-none px-3 py-2 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
            value === tab.id
              ? 'bg-cv-accent text-white shadow-sm'
              : 'text-cv-muted hover:text-cv-text hover:bg-cv-deep/40'
          }`}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
