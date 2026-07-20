import EvidencePolicyForm from '@/components/evidence/EvidencePolicyForm';
import type { EvidencePolicy } from '@/lib/evidencePolicy';

interface EvidencePolicyPanelProps {
  policy: EvidencePolicy;
  onChange: (p: EvidencePolicy) => void;
}

export default function EvidencePolicyPanel({ policy, onChange }: EvidencePolicyPanelProps) {
  return <EvidencePolicyForm policy={policy} onChange={onChange} variant="studio" />;
}
