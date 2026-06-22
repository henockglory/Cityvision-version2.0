import catalog from '../../../shared/detection-classes.json';

export interface ClassGroup {
  id: string;
  label_fr: string;
  label_en: string;
}

export const CLASS_GROUPS = catalog.groups as ClassGroup[];
export const GROUP_MEMBERS = catalog.group_members as Record<string, string[]>;
export const COCO_CLASSES = catalog.coco_classes as string[];

export function classLabel(id: string, lang: 'fr' | 'en' = 'fr'): string {
  const group = CLASS_GROUPS.find((g) => g.id === id);
  if (group) return lang === 'fr' ? group.label_fr : group.label_en;
  return id;
}

export function isGroupId(id: string): boolean {
  return CLASS_GROUPS.some((g) => g.id === id);
}

export function matchesClassFilter(className: string, filter: string): boolean {
  if (!filter || filter === 'any') return true;
  if (filter === className) return true;
  const members = GROUP_MEMBERS[filter];
  if (members?.length) return members.includes(className);
  return false;
}
