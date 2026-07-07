import type { Alert, Event, Rule } from '@/types';
import { parseEvidenceSnapshot } from '@/lib/evidence';

type CondNode = {
  op?: string;
  field?: string;
  value?: unknown;
  children?: CondNode[];
};

const PRESENCE_TEMPLATES = new Set([
  'tpl-loitering',
  'tpl-presence',
  'tpl-person-stopped',
  'tpl-vehicle-stopped',
]);

export function ruleCameraId(rule: Rule): string {
  const b = rule.definition?.bindings as Record<string, unknown> | undefined;
  return String(b?.camera_id ?? rule.definition?.camera_id ?? '');
}

function collectEventTypes(node: CondNode | undefined, out: Set<string>): void {
  if (!node) return;
  const op = String(node.op ?? '').toUpperCase();
  if (['OR', 'OU', 'AND', 'ET'].includes(op)) {
    for (const c of node.children ?? []) collectEventTypes(c, out);
    return;
  }
  if (node.field === 'event_type' || node.field === 'event') {
    if (node.value != null) out.add(String(node.value));
  }
  for (const c of node.children ?? []) collectEventTypes(c, out);
}

export function enabledRuleEventTypes(rules: Rule[]): Set<string> {
  const out = new Set<string>();
  for (const r of rules) {
    if (!r.enabled) continue;
    const cond = (r.definition?.condition ?? r.definition?.conditions) as CondNode | undefined;
    collectEventTypes(cond, out);
  }
  return out;
}

/** Event types for rules bound to the active demo camera(s) only. */
export function enabledRuleEventTypesForCameras(rules: Rule[], scopeCameraIds: string[]): Set<string> {
  if (scopeCameraIds.length === 0) return enabledRuleEventTypes(rules);
  const scoped = rules.filter((r) => {
    if (!r.enabled) return false;
    const cam = ruleCameraId(r);
    return cam !== '' && scopeCameraIds.includes(cam);
  });
  return enabledRuleEventTypes(scoped);
}

export function rulesForScopeCameras(rules: Rule[], scopeCameraIds: string[]): Rule[] {
  if (scopeCameraIds.length === 0) return rules;
  return rules.filter((r) => {
    if (!r.enabled) return false;
    const cam = ruleCameraId(r);
    return cam !== '' && scopeCameraIds.includes(cam);
  });
}

export function hasPresenceRule(rules: Rule[]): boolean {
  return rules.some((r) => {
    if (!r.enabled) return false;
    const tpl = String((r.definition?.bindings as Record<string, unknown> | undefined)?.template_id ?? '');
    return PRESENCE_TEMPLATES.has(tpl);
  });
}

/** Camera scope for live demo feeds: active video when no rules, else rule cameras (prefer active match). */
export function feedScopeCameraIds(
  enabledRuleCameraIds: string[],
  zoneCameraId: string | undefined,
): string[] {
  if (enabledRuleCameraIds.length > 0) {
    if (zoneCameraId && enabledRuleCameraIds.includes(zoneCameraId)) {
      return [zoneCameraId];
    }
    return [...enabledRuleCameraIds];
  }
  if (zoneCameraId) return [zoneCameraId];
  return [];
}

function eventScore(e: Event, ruleTypes: Set<string>): number {
  let score = new Date(e.timestamp).getTime();
  if (ruleTypes.has(e.type)) score += 1e15;
  if (eventHasEvidence(e)) score += 5e14;
  return score;
}

function eventHasEvidence(e: Event): boolean {
  const snap = parseEvidenceSnapshot(e.evidenceSnapshot);
  return Boolean(
    snap.package?.clip?.url || snap.package?.clip?.asset_id
    || (snap.package?.images?.length ?? 0) > 0,
  );
}

/** Collapse burst duplicates (same type/camera within a few seconds) for demo UI. */
function dedupeBurstEvents(events: Event[], windowMs = 3_000): Event[] {
  const kept: Event[] = [];
  for (const e of events) {
    const ts = new Date(e.timestamp).getTime();
    const burst = kept.some((o) => (
      o.type === e.type
      && o.cameraId === e.cameraId
      && Math.abs(new Date(o.timestamp).getTime() - ts) < windowMs
    ));
    if (!burst) kept.push(e);
  }
  return kept;
}

export function filterDemoEvents(
  events: Event[],
  scopeCameraIds: string[],
  enabledRules: Rule[],
  isDemoPayload: (raw: unknown) => boolean,
): Event[] {
  if (scopeCameraIds.length === 0) return [];
  const scopedRules = rulesForScopeCameras(enabledRules, scopeCameraIds);
  const ruleTypes = enabledRuleEventTypesForCameras(enabledRules, scopeCameraIds);
  const hasRules = scopedRules.length > 0;

  const filtered = events
    .filter((e) => {
      if (isDemoPayload(e.payload)) {
        if (e.cameraId && scopeCameraIds.length > 0 && !scopeCameraIds.includes(e.cameraId)) return false;
      } else if (!e.cameraId || !scopeCameraIds.includes(e.cameraId)) {
        return false;
      }
      if (!hasRules) return true;
      if (!ruleTypes.has(e.type)) return false;
      return eventHasEvidence(e);
    })
    .sort((a, b) => eventScore(b, ruleTypes) - eventScore(a, ruleTypes));
  return dedupeBurstEvents(filtered);
}

export function filterDemoAlerts(
  alerts: Alert[],
  scopeCameraIds: string[],
  isDemoPayload: (raw: unknown) => boolean,
  enabledRules: Rule[] = [],
): Alert[] {
  if (scopeCameraIds.length === 0) return [];
  const scopedRuleIds = new Set(
    rulesForScopeCameras(enabledRules, scopeCameraIds).map((r) => r.id),
  );
  return alerts
    .filter((a) => {
      if (isDemoPayload(a.metadata)) {
        if (a.cameraId && scopeCameraIds.length > 0 && !scopeCameraIds.includes(a.cameraId)) return false;
      } else if (!a.cameraId || !scopeCameraIds.includes(a.cameraId)) {
        return false;
      }
      if (scopedRuleIds.size > 0 && a.ruleId && !scopedRuleIds.has(a.ruleId)) {
        return false;
      }
      const snap = parseEvidenceSnapshot(a.evidenceSnapshot);
      return Boolean(
        snap.package?.clip?.url || snap.package?.clip?.asset_id
        || (snap.package?.images?.length ?? 0) > 0,
      );
    })
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
}

export function findMatchingAlert(event: Event, alerts: Alert[]): Alert | undefined {
  const payloadEventId = String(event.payload?.event_id ?? '');
  if (payloadEventId) {
    const byId = alerts.find((a) => {
      const meta = a.metadata ?? {};
      const nested = meta.payload as Record<string, unknown> | undefined;
      return String(meta.event_id ?? nested?.event_id ?? '') === payloadEventId;
    });
    if (byId) return byId;
  }
  const eventTs = new Date(event.timestamp).getTime();
  return alerts.find((a) => {
    if (a.cameraId !== event.cameraId) return false;
    const alertTs = new Date(a.timestamp).getTime();
    if (Math.abs(alertTs - eventTs) > 120_000) return false;
    return Boolean(parseEvidenceSnapshot(a.evidenceSnapshot).package);
  });
}

export function resolvePreviewEvidence(
  event: Event | undefined,
  alert: Alert | undefined,
  allAlerts: Alert[],
): {
  evidence: Record<string, unknown> | undefined;
  ruleId?: string;
  cameraId?: string;
  title?: string;
} {
  if (alert) {
    return {
      evidence: alert.evidenceSnapshot,
      ruleId: alert.ruleId,
      cameraId: alert.cameraId,
      title: alert.message,
    };
  }
  if (event) {
    const matched = findMatchingAlert(event, allAlerts);
    if (matched?.evidenceSnapshot && parseEvidenceSnapshot(matched.evidenceSnapshot).package) {
      return {
        evidence: matched.evidenceSnapshot,
        ruleId: matched.ruleId,
        cameraId: matched.cameraId,
        title: event.typeLabel ?? event.type,
      };
    }
    return {
      evidence: event.evidenceSnapshot,
      cameraId: event.cameraId,
      title: event.typeLabel ?? event.type,
    };
  }
  return { evidence: undefined };
}

export function demoVideoLabelForCamera(
  cameraId: string,
  cameras: { id: string; name: string; metadata?: Record<string, unknown> }[],
  videos: { id: string; name: string }[],
): string {
  const cam = cameras.find((c) => c.id === cameraId);
  const videoId = String(cam?.metadata?.demo_video_id ?? '');
  const video = videos.find((v) => v.id === videoId);
  return video?.name ?? cam?.name ?? cameraId.slice(0, 8);
}

export function demoVideoIdForCamera(
  cameraId: string,
  cameras: { id: string; metadata?: Record<string, unknown> }[],
): string | undefined {
  const cam = cameras.find((c) => c.id === cameraId);
  const videoId = String(cam?.metadata?.demo_video_id ?? '');
  return videoId || undefined;
}

export function isVideoMismatch(
  enabledRuleCameraIds: string[],
  zoneCameraId: string | undefined,
): boolean {
  if (enabledRuleCameraIds.length === 0 || !zoneCameraId) return false;
  return !enabledRuleCameraIds.includes(zoneCameraId);
}
