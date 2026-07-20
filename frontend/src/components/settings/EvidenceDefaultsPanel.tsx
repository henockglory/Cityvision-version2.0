import { useEffect, useState } from 'react';
import { orgApi } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import EvidencePolicyForm from '@/components/evidence/EvidencePolicyForm';
import {
  DEFAULT_EVIDENCE_POLICY,
  normalizeEvidencePolicy,
  type EvidencePolicy,
} from '@/lib/evidencePolicy';

export default function EvidenceDefaultsPanel() {
  const orgId = useAuthStore((s) => s.orgId);
  const [policy, setPolicy] = useState<EvidencePolicy>(DEFAULT_EVIDENCE_POLICY);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    if (!orgId) return;
    void orgApi.get(orgId).then((r) => {
      const prefs = r.data.notification_prefs ?? {};
      const raw = (prefs as Record<string, unknown>).evidence_defaults as Partial<EvidencePolicy> | undefined;
      setPolicy(normalizeEvidencePolicy(raw));
    });
  }, [orgId]);

  const save = async () => {
    if (!orgId) return;
    const r = await orgApi.get(orgId);
    const prefs = { ...(r.data.notification_prefs ?? {}), evidence_defaults: policy };
    await orgApi.update(orgId, { notification_prefs: prefs });
    setMsg('Défauts preuves enregistrés — appliqués aux nouvelles règles.');
  };

  return (
    <div id="evidence-policy-panel" className="space-y-4">
      <p className="text-sm text-cv-muted">
        Ces paramètres servent de base lors de l&apos;activation d&apos;une nouvelle règle (clip automatique H.264, images, cadre).
      </p>
      <EvidencePolicyForm
        policy={policy}
        onChange={setPolicy}
        variant="settings"
        showEnabledToggle={false}
      />
      <button type="button" className="cv-btn-primary text-sm" onClick={() => void save()}>
        Enregistrer les défauts
      </button>
      {msg && <p className="text-xs text-emerald-500">{msg}</p>}
    </div>
  );
}
