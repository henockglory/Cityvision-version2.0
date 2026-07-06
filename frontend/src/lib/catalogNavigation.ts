import catalogNavigation from '@shared/catalog-navigation.json';
import type { RuleCatalogTemplate } from '@/types';

export type DeploymentScope = 'all' | 'national' | 'enterprise' | 'domestic';

export interface CatalogNavEntry {
  megaId: string;
  subId: string;
  searchTags?: string[];
}

export interface CatalogSubGroupNode {
  id: string;
  megaId: string;
  order: number;
  templates: RuleCatalogTemplate[];
}

export interface CatalogMegaGroupNode {
  id: string;
  order: number;
  muted?: boolean;
  subGroups: CatalogSubGroupNode[];
  templateCount: number;
}

const nav = catalogNavigation as {
  megaGroups: Array<{
    id: string;
    order: number;
    muted?: boolean;
    scopeOrder?: Partial<Record<DeploymentScope, number>>;
  }>;
  subGroups: Array<{ id: string; megaId: string; order: number }>;
  templates: Record<string, CatalogNavEntry>;
};

const megaById = new Map(nav.megaGroups.map((m) => [m.id, m]));
const subMetaById = new Map(nav.subGroups.map((s) => [s.id, s]));

export function resolveTemplateNav(templateId: string): CatalogNavEntry {
  return (
    nav.templates[templateId] ?? {
      megaId: 'objects',
      subId: 'objects_scene',
      searchTags: [],
    }
  );
}

function megaOrderForScope(megaId: string, scope: DeploymentScope): number {
  const mega = megaById.get(megaId);
  if (!mega) return 999;
  const scoped = mega.scopeOrder?.[scope];
  if (scoped != null) return scoped;
  return mega.order;
}

export function buildCatalogTree(
  templates: RuleCatalogTemplate[],
  deploymentScope: DeploymentScope = 'all',
): CatalogMegaGroupNode[] {
  const megaMap = new Map<string, Map<string, RuleCatalogTemplate[]>>();

  for (const tpl of templates) {
    const { megaId, subId } = resolveTemplateNav(tpl.id);
    if (!megaMap.has(megaId)) megaMap.set(megaId, new Map());
    const subMap = megaMap.get(megaId)!;
    if (!subMap.has(subId)) subMap.set(subId, []);
    subMap.get(subId)!.push(tpl);
  }

  const megaNodes: CatalogMegaGroupNode[] = [];

  for (const [megaId, subMap] of megaMap) {
    const megaMeta = megaById.get(megaId);
    const subGroups: CatalogSubGroupNode[] = [];

    for (const [subId, items] of subMap) {
      const subMeta = subMetaById.get(subId);
      subGroups.push({
        id: subId,
        megaId,
        order: subMeta?.order ?? 999,
        templates: [...items].sort((a, b) => a.name.localeCompare(b.name, 'fr')),
      });
    }

    subGroups.sort((a, b) => a.order - b.order);
    const templateCount = subGroups.reduce((n, sg) => n + sg.templates.length, 0);
    if (templateCount === 0) continue;

    megaNodes.push({
      id: megaId,
      order: megaOrderForScope(megaId, deploymentScope),
      muted: megaMeta?.muted,
      subGroups,
      templateCount,
    });
  }

  return megaNodes.sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
}

export function catalogSearchHaystack(
  tpl: RuleCatalogTemplate,
  labelForMega: (id: string) => string,
  labelForSub: (id: string) => string,
): string {
  const { megaId, subId, searchTags = [] } = resolveTemplateNav(tpl.id);
  return [
    tpl.name,
    tpl.category ?? '',
    tpl.capability_id ?? '',
    tpl.human_description ?? '',
    tpl.role_summary_fr ?? '',
    labelForMega(megaId),
    labelForSub(subId),
    ...searchTags,
  ]
    .join(' ')
    .toLowerCase();
}

/** Pick default open mega + sub for scope (most operational templates). */
export function defaultOpenGroups(
  tree: CatalogMegaGroupNode[],
  isOperational: (tpl: RuleCatalogTemplate) => boolean,
): { megaId: string; subId: string } | null {
  for (const mega of tree) {
    let bestSub: CatalogSubGroupNode | null = null;
    let bestScore = -1;
    for (const sub of mega.subGroups) {
      const score = sub.templates.filter(isOperational).length;
      if (score > bestScore) {
        bestScore = score;
        bestSub = sub;
      }
    }
    if (bestSub && bestSub.templates.length > 0) {
      return { megaId: mega.id, subId: bestSub.id };
    }
  }
  const first = tree[0];
  const firstSub = first?.subGroups[0];
  if (first && firstSub) return { megaId: first.id, subId: firstSub.id };
  return null;
}

export function allSubGroupIds(): string[] {
  return nav.subGroups.map((s) => s.id);
}

export function allMegaGroupIds(): string[] {
  return nav.megaGroups.map((m) => m.id);
}
