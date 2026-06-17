interface SegmentedTab {
  id: string;
  label: string;
}

interface SegmentedTabsProps {
  tabs: SegmentedTab[];
  value: string;
  onChange: (id: string) => void;
  className?: string;
}

export default function SegmentedTabs({ tabs, value, onChange, className = '' }: SegmentedTabsProps) {
  return (
    <div
      className={`inline-flex p-1 rounded-lg bg-cv-deep/50 border border-cv-border/60 ${className}`}
      role="tablist"
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={value === tab.id}
          className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
            value === tab.id
              ? 'bg-cv-accent text-white shadow-sm'
              : 'text-cv-muted hover:text-cv-text'
          }`}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
