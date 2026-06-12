import { useTranslation } from 'react-i18next';
import { Plus, User, Shield } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import LoadingState from '@/components/ui/LoadingState';
import { useUsers } from '@/hooks/api/queries';
import { useSound } from '@/hooks/useSound';

export default function Users() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const { data: users = [], isLoading } = useUsers();

  if (isLoading) return <LoadingState />;

  return (
    <div>
      <PageHeader
        title={t('users.title')}
        actions={
          <button type="button" onClick={() => playClick()} className="cv-btn-primary">
            <Plus className="w-4 h-4" />
            {t('users.add')}
          </button>
        }
      />

      <div className="cv-card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-cv-border">
              <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">Utilisateur</th>
              <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">Email</th>
              <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">{t('users.role')}</th>
              <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">{t('users.lastLogin')}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id} className="border-b border-cv-border/50 hover:bg-cv-accent/5 transition-colors">
                <td className="px-5 py-4">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-cv-accent/15 border border-cv-accent/25 flex items-center justify-center">
                      <User className="w-4 h-4 text-cv-accent" />
                    </div>
                    <span className="font-medium">{user.username}</span>
                  </div>
                </td>
                <td className="px-5 py-4 text-sm text-cv-muted">{user.email}</td>
                <td className="px-5 py-4">
                  <span className="cv-badge border border-cv-accent/30 bg-cv-accent/10 text-cv-accent flex items-center gap-1 w-fit">
                    <Shield className="w-3 h-3" />
                    {t(`roles.${user.role}`)}
                  </span>
                </td>
                <td className="px-5 py-4 text-sm text-cv-muted">
                  {user.lastLogin ? new Date(user.lastLogin).toLocaleString() : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
