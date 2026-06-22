export default function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-lg bg-cv-border/40 ${className}`}
      aria-hidden
    />
  );
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <Skeleton className="lg:col-span-7 h-56" />
        <Skeleton className="lg:col-span-5 h-56" />
      </div>
    </div>
  );
}

export function MapSkeleton() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
      <Skeleton className="lg:col-span-8 h-[480px]" />
      <Skeleton className="lg:col-span-4 h-[480px]" />
    </div>
  );
}

export function RulesSkeleton() {
  return (
    <div className="space-y-5">
      <Skeleton className="h-10 w-64" />
      <Skeleton className="h-96" />
      <Skeleton className="h-48" />
    </div>
  );
}
