import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, X } from 'lucide-react';
import InfoTip from '@/components/ui/InfoTip';
import DialogTourHelpButton from '@/components/ui/DialogTourHelpButton';
import { useDialogTour } from '@/hooks/useDialogTour';
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
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<UserRole>('operator');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const startTour = useDialogTour('addUser', open);

  if (!open) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (password.length < 12) {
      setError(t('users.dialog.passwordMin'));
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
      setError(t('users.dialog.submitError'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <form
        id="add-user-dialog"
        onSubmit={(e) => void handleSubmit(e)}
        className="cv-card w-full max-w-md p-6 shadow-glow-lg border-cv-electric/30"
      >
        <div className="flex items-center justify-between mb-4 gap-2">
          <h2 className="font-display text-lg font-semibold">{t('users.dialog.title')}</h2>
          <div className="flex items-center gap-1">
            <DialogTourHelpButton onClick={() => startTour()} />
            <button type="button" onClick={onClose} className="cv-btn-ghost p-2" aria-label={t('common.close')}>
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="space-y-3">
          <div id="add-user-name">
            <label className="cv-label flex items-center gap-1">
              {t('users.dialog.fullName')}
              <InfoTip helpKey="userFullName" content={t('users.dialog.fullNameHint')} />
            </label>
            <input className="cv-input" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          </div>
          <div id="add-user-email">
            <label className="cv-label flex items-center gap-1">
              {t('users.dialog.email')}
              <InfoTip helpKey="userEmail" content={t('users.dialog.emailHint')} />
            </label>
            <input type="email" className="cv-input" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div id="add-user-password">
            <label className="cv-label flex items-center gap-1">
              {t('users.dialog.password')}
              <InfoTip helpKey="userPassword" content={t('users.dialog.passwordHint')} />
            </label>
            <input
              type="password"
              className="cv-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={12}
            />
          </div>
          <div id="add-user-role">
            <label className="cv-label flex items-center gap-1">
              {t('users.role')}
              <InfoTip helpKey="userRole" content={t('users.dialog.roleHint')} />
            </label>
            <select className="cv-input" value={role} onChange={(e) => setRole(e.target.value as UserRole)}>
              <option value="admin">{t('users.dialog.roleAdmin')}</option>
              <option value="operator">{t('users.dialog.roleOperator')}</option>
              <option value="viewer">{t('users.dialog.roleViewer')}</option>
            </select>
          </div>
        </div>

        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

        <div className="flex gap-3 mt-6">
          <button type="button" onClick={onClose} className="cv-btn-secondary flex-1">
            {t('common.cancel')}
          </button>
          <button id="add-user-submit" type="submit" disabled={submitting} className="cv-btn-primary flex-1">
            {submitting ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : t('users.dialog.submit')}
          </button>
        </div>
      </form>
    </div>
  );
}
