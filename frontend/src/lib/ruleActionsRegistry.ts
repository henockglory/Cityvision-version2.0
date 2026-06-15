export interface RuleActionDef {
  type: string;
  family: string;
  label: string;
  description: string;
  executed: boolean;
  defaultConfig?: Record<string, unknown>;
}

export const ACTION_FAMILIES: Record<string, string> = {
  notification: 'Notification',
  recording: 'Enregistrement',
  counting: 'Comptage',
  archive: 'Archivage',
  alert: 'Alerte',
  incident: 'Incident',
};

/** Actions réellement exécutées localement (registre honnête v3). */
export const RULE_ACTIONS_REGISTRY: RuleActionDef[] = [
  { type: 'alert', family: 'alert', label: 'Créer une alerte', description: 'Enregistre une alerte avec preuves dans le tableau de bord.', executed: true, defaultConfig: { severity: 'medium' } },
  { type: 'alert', family: 'alert', label: 'Alerte haute priorité', description: 'Alerte sévérité élevée.', executed: true, defaultConfig: { severity: 'high' } },
  { type: 'alert', family: 'alert', label: 'Alerte critique', description: 'Alerte sévérité critique.', executed: true, defaultConfig: { severity: 'critical' } },
  { type: 'record', family: 'recording', label: 'Clip 15 s', description: 'Capture vidéo ffmpeg 15 secondes.', executed: true, defaultConfig: { duration_sec: 15 } },
  { type: 'record', family: 'recording', label: 'Clip 30 s', description: 'Capture vidéo ffmpeg 30 secondes.', executed: true, defaultConfig: { duration_sec: 30 } },
  { type: 'record', family: 'recording', label: 'Clip 60 s', description: 'Capture vidéo ffmpeg 60 secondes.', executed: true, defaultConfig: { duration_sec: 60 } },
  { type: 'notify', family: 'notification', label: 'E-mail', description: 'Notification SMTP si configuré.', executed: true, defaultConfig: { channel: 'email' } },
  { type: 'webhook', family: 'notification', label: 'Webhook local', description: 'POST vers URL locale (WEBHOOK_LOCAL_URL ou config).', executed: true, defaultConfig: {} },
  { type: 'log', family: 'notification', label: 'Journal fichier', description: 'Append dans le fichier audit actions local.', executed: true, defaultConfig: {} },
  { type: 'counter', family: 'counting', label: 'Incrémenter compteur', description: 'Compteur par règle (table rule_counters).', executed: true, defaultConfig: { delta: 1 } },
  { type: 'counter', family: 'counting', label: 'Compteur +5', description: 'Incrémente le compteur de 5.', executed: true, defaultConfig: { delta: 5 } },
  { type: 'archive_auto', family: 'archive', label: 'Archivage auto (5 min)', description: 'Archive les alertes ouvertes de la règle après 5 min.', executed: true, defaultConfig: { after_minutes: 5 } },
  { type: 'archive_auto', family: 'archive', label: 'Archivage auto (15 min)', description: 'Archive les alertes ouvertes après 15 min.', executed: true, defaultConfig: { after_minutes: 15 } },
  { type: 'incident', family: 'incident', label: 'Créer incident', description: 'Ouvre un incident lié à la détection.', executed: true, defaultConfig: { severity: 'high' } },
  { type: 'incident', family: 'incident', label: 'Incident moyen', description: 'Incident sévérité moyenne.', executed: true, defaultConfig: { severity: 'medium' } },
  { type: 'notify', family: 'notification', label: 'SMS', description: 'Non disponible sans passerelle SMS locale.', executed: false, defaultConfig: { channel: 'sms' } },
  { type: 'ptz', family: 'recording', label: 'Relay PTZ', description: 'Non disponible sans relais PTZ local.', executed: false },
];

export function actionsByFamily(): Record<string, RuleActionDef[]> {
  const out: Record<string, RuleActionDef[]> = {};
  for (const a of RULE_ACTIONS_REGISTRY) {
    if (!out[a.family]) out[a.family] = [];
    out[a.family].push(a);
  }
  return out;
}

export function defaultActionsSelection(): string[] {
  const first = RULE_ACTIONS_REGISTRY.find((a) => a.type === 'alert' && a.executed);
  return first ? [actionKey(first)] : [];
}

export function actionKey(act: RuleActionDef): string {
  return `${act.type}:${act.label}`;
}

export function buildActionsPayload(
  selectedKeys: string[],
  severity: string,
  email?: string,
) {
  return selectedKeys.map((key) => {
    const reg = RULE_ACTIONS_REGISTRY.find((a) => actionKey(a) === key);
    if (!reg) return { type: key.split(':')[0], config: {} };
    const cfg = { ...(reg.defaultConfig ?? {}) };
    if (reg.type === 'alert' && !cfg.severity) cfg.severity = severity;
    if (reg.type === 'notify' && email) {
      cfg.channel = 'email';
      cfg.to = email;
    }
    return { type: reg.type, config: cfg };
  });
}

export function actionsFromRule(
  actions: Array<{ type: string; config?: Record<string, unknown> }> | undefined,
): string[] {
  if (!actions?.length) return defaultActionsSelection();
  const keys: string[] = [];
  for (const act of actions) {
    const match = RULE_ACTIONS_REGISTRY.find((r) => {
      if (r.type !== act.type) return false;
      const cfg = act.config ?? {};
      if (r.type === 'alert' && cfg.severity && r.defaultConfig?.severity) {
        return r.defaultConfig.severity === cfg.severity;
      }
      if (r.type === 'record' && cfg.duration_sec && r.defaultConfig?.duration_sec) {
        return r.defaultConfig.duration_sec === cfg.duration_sec;
      }
      if (r.type === 'archive_auto' && cfg.after_minutes && r.defaultConfig?.after_minutes) {
        return r.defaultConfig.after_minutes === cfg.after_minutes;
      }
      return r.executed;
    });
    if (match) keys.push(actionKey(match));
    else keys.push(`${act.type}:${act.type}`);
  }
  return keys.length ? [...new Set(keys)] : defaultActionsSelection();
}

export function executedActionsOnly(): RuleActionDef[] {
  return RULE_ACTIONS_REGISTRY.filter((a) => a.executed);
}
