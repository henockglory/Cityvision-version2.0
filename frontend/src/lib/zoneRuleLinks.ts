import type { Rule } from '@/types';

export interface ZoneRuleLink {
  ruleId: string;
  ruleName: string;
  templateId: string;
  eventType: string;
  enabled: boolean;
  misconfigured: boolean;
  misconfiguredReason?: string;
}

export interface ZoneRuleLinkContext {
  zones: Array<{ name: string; behavior?: string }>;
  lines: Array<{ name: string; behavior?: string }>;
  capabilityBehaviors?: Array<{ id: string; emits: string[] }>;
}

function binding(def: Record<string, unknown> | undefined) {
  return (def?.bindings ?? {}) as Record<string, unknown>;
}

function primaryEvent(def: Record<string, unknown> | undefined): string {
  const walk = (node: unknown): string => {
    if (!node || typeof node !== 'object') return '';
    const n = node as Record<string, unknown>;
    if (n.op === 'eq' && (n.field === 'event_type' || n.field === 'event') && typeof n.value === 'string') {
      return n.value;
    }
    if (Array.isArray(n.children)) {
      for (const c of n.children) {
        const ev = walk(c);
        if (ev) return ev;
      }
    }
    return '';
  };
  return walk(def?.condition);
}

function behaviorEmitsEvent(
  behaviorId: string | undefined,
  eventType: string,
  behaviors: Array<{ id: string; emits: string[] }>,
): boolean {
  if (!eventType) return true;
  const id = behaviorId ?? '';
  if (!id) return false;
  const entry = behaviors.find((b) => b.id === id);
  if (!entry) return false;
  return entry.emits.includes(eventType);
}

function diagnoseRuleForZone(
  focusZone: string,
  rule: Rule,
  ctx: ZoneRuleLinkContext,
): { misconfigured: boolean; reason?: string } {
  const b = binding(rule.definition as Record<string, unknown>);
  const ev = primaryEvent(rule.definition as Record<string, unknown>);
  const caps = ctx.capabilityBehaviors ?? [];

  const viaLine = b.line_name === focusZone;
  const viaZone = b.zone_name === focusZone || b.zone_name_2 === focusZone;

  if (viaLine) {
    const line = ctx.lines.find((l) => l.name === focusZone);
    if (!line) {
      return { misconfigured: true, reason: 'Ligne introuvable en base' };
    }
    const lineBehavior = line.behavior ?? 'line_cross';
    if (ev && caps.length > 0 && !behaviorEmitsEvent(lineBehavior, ev, caps)) {
      return {
        misconfigured: true,
        reason: `Comportement incompatible (n'émet pas ${ev})`,
      };
    }
    return { misconfigured: false };
  }

  if (viaZone) {
    const zone = ctx.zones.find((z) => z.name === focusZone);
    if (!zone) {
      return { misconfigured: true, reason: 'Zone introuvable en base' };
    }
    if (ev && caps.length > 0 && !behaviorEmitsEvent(zone.behavior, ev, caps)) {
      const beh = zone.behavior ?? 'non défini';
      return {
        misconfigured: true,
        reason: `Comportement « ${beh} » n'émet pas ${ev}`,
      };
    }
    return { misconfigured: false };
  }

  return { misconfigured: false };
}

export function rulesLinkedToZone(
  zoneName: string,
  rules: Rule[],
  ctx?: ZoneRuleLinkContext,
): ZoneRuleLink[] {
  if (!zoneName) return [];
  return rules
    .filter((r) => {
      const b = binding(r.definition as Record<string, unknown>);
      return b.zone_name === zoneName || b.zone_name_2 === zoneName || b.line_name === zoneName;
    })
    .map((r) => {
      const b = binding(r.definition as Record<string, unknown>);
      const tpl = String(b.template_id ?? 'custom');
      const ev = primaryEvent(r.definition as Record<string, unknown>);
      const diag = ctx ? diagnoseRuleForZone(zoneName, r, ctx) : { misconfigured: false as const };
      return {
        ruleId: r.id,
        ruleName: r.name,
        templateId: tpl,
        eventType: ev,
        enabled: r.enabled,
        misconfigured: diag.misconfigured,
        misconfiguredReason: diag.reason,
      };
    });
}

export function zoneLinkedToRule(
  zoneName: string | undefined,
  lineName: string | undefined,
  zones: Array<{ name: string; behavior?: string }>,
  lines: Array<{ name: string; behavior?: string }>,
  eventType?: string,
  capabilityBehaviors?: Array<{ id: string; emits: string[] }>,
): { found: boolean; behavior?: string; misconfigured: boolean; reason?: string } {
  const caps = capabilityBehaviors ?? [];

  if (lineName) {
    const line = lines.find((l) => l.name === lineName);
    if (!line) {
      return { found: false, misconfigured: true, reason: 'Ligne introuvable en base' };
    }
    const lineBehavior = line.behavior ?? 'line_cross';
    if (eventType && caps.length > 0 && !behaviorEmitsEvent(lineBehavior, eventType, caps)) {
      return {
        found: true,
        behavior: lineBehavior,
        misconfigured: true,
        reason: `Comportement incompatible (n'émet pas ${eventType})`,
      };
    }
    return { found: true, behavior: lineBehavior, misconfigured: false };
  }

  if (!zoneName) return { found: false, misconfigured: false };

  const zone = zones.find((z) => z.name === zoneName);
  if (!zone) {
    return { found: false, misconfigured: true, reason: 'Zone introuvable en base' };
  }

  if (eventType && caps.length > 0 && !behaviorEmitsEvent(zone.behavior, eventType, caps)) {
    const beh = zone.behavior ?? 'non défini';
    return {
      found: true,
      behavior: zone.behavior,
      misconfigured: true,
      reason: `Comportement « ${beh} » n'émet pas ${eventType}`,
    };
  }

  return { found: true, behavior: zone.behavior, misconfigured: false };
}

/** Template IDs compatible with a zone behavior via capabilities menu emits. */
export function templateIdsForBehavior(
  behaviorId: string | undefined,
  capabilityBehaviors: Array<{ id: string; compatible_templates?: string[]; emits: string[] }>,
): string[] {
  if (!behaviorId) return [];
  const entry = capabilityBehaviors.find((b) => b.id === behaviorId);
  if (!entry) return [];
  return entry.compatible_templates ?? [];
}
