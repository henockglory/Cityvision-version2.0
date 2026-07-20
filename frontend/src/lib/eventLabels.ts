import eventLabels from '../../../shared/event-labels.fr.json';

export function labelForEventType(type: string, labelFr?: string): string {
  if (labelFr) return labelFr;
  const labels = eventLabels as Record<string, string>;
  return labels[type] ?? type.replace(/_/g, ' ');
}
