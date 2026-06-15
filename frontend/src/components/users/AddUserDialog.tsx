import { useState, type FormEvent } from 'react';
import { Loader2, X } from 'lucide-react';
import type { UserRole } from '@/types';

interface AddUserDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: {
    email: string;
    full_name: string;
    password: string;
    role: UserRole;
  }) => Promise<void>;
}

export default function AddUserDialog({ open, onClose, onSubmit }: AddUserDialogProps) {
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<UserRole>('operator');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  if (!open) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (password.length < 12) {
      setError('Mot de passe minimum 12 caractères.');
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit({ email, full_name: fullName, password, role });
      setEmail('');
      setFullName('');
      setPassword('');
      onClose();
    } catch {
      setError('Échec — vérifiez l’email et vos droits administrateur.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <form
        onSubmit={(e) => void handleSubmit(e)}
        className="cv-card w-full max-w-md p-6 shadow-glow-lg border-cv-electric/30"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display text-lg font-semibold">Inviter un utilisateur</h2>
          <button type="button" onClick={onClose} className="cv-btn-ghost p-2">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="cv-label">Nom complet</label>
            <input className="cv-input" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          </div>
          <div>
            <label className="cv-label">Email</label>
            <input type="email" className="cv-input" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div>
            <label className="cv-label">Mot de passe temporaire</label>
            <input
              type="password"
              className="cv-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={12}
            />
          </div>
          <div>
            <label className="cv-label">Rôle</label>
            <select className="cv-input" value={role} onChange={(e) => setRole(e.target.value as UserRole)}>
              <option value="admin">Administrateur</option>
              <option value="operator">Opérateur</option>
              <option value="viewer">Observateur</option>
            </select>
          </div>
        </div>

        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

        <div className="flex gap-3 mt-6">
          <button type="button" onClick={onClose} className="cv-btn-secondary flex-1">
            Annuler
          </button>
          <button type="submit" disabled={submitting} className="cv-btn-primary flex-1">
            {submitting ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : 'Créer le compte'}
          </button>
        </div>
      </form>
    </div>
  );
}
