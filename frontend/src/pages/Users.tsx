import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, User, Shield, Users as UsersIcon, UserX } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import LoadingState from '@/components/ui/LoadingState';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import AddUserDialog from '@/components/users/AddUserDialog';
import { useUsers, useCreateUser, useUpdateUser } from '@/hooks/api/queries';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';
import { useSound } from '@/hooks/useSound';
import type { UserRole } from '@/types';

const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: 'admin', label: 'Administrateur' },
  { value: 'operator', label: 'Opérateur' },
  { value: 'viewer', label: 'Observateur' },
];

export default function UsersPage() {
  const { t } = useTranslation();
  const { playClick, playSonar } = useSound();
  const startTour = useAutoPageTour('users');
  const { data: users = [], isLoading, isError, refetch } = useUsers();
  const createUser = useCreateUser();
  const updateUser = useUpdateUser();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const handleCreate = async (data: {
    email: string;
    full_name: string;
    password: string;
    role: UserRole;
  }) => {
    await createUser.mutateAsync(data);
    playSonar();
  };

  const changeRole = async (userId: string, role: UserRole) => {
    playClick();
    setBusyId(userId);
    try {
      await updateUser.mutateAsync({ userId, body: { role } });
    } finally {
      setBusyId(null);
    }
  };

  const toggleActive = async (userId: string, isActive: boolean) => {
    playClick();
    setBusyId(userId);
    try {
      await updateUser.mutateAsync({ userId, body: { is_active: !isActive } });
    } finally {
      setBusyId(null);
    }
  };

  if (isLoading) return <LoadingState />;

  if (isError) {
    return (
      <div>
        <PageHeader title={t('users.title')} onHelpTour={startTour} />
        <ErrorState onRetry={() => void refetch()} />
      </div>
    );
  }

  return (
    <div>
      <AddUserDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onSubmit={handleCreate}
      />

      <PageHeader
        title={t('users.title')}
        subtitle={t('users.subtitle', 'Membres de l’organisation et rôles RBAC')}
        onHelpTour={startTour}
        actions={
          <button
            type="button"
            onClick={() => {
              playClick();
              setDialogOpen(true);
            }}
            className="cv-btn-primary"
          >
            <Plus className="w-4 h-4" />
            {t('users.add')}
          </button>
        }
      />

      <p className="text-sm text-cv-muted mb-4">
        Gérez les accès : administrateur (tout), opérateur (caméras/règles), observateur (lecture seule).
      </p>

      {users.length === 0 ? (
        <EmptyState title={t('users.empty')} hint={t('users.emptyHint')} icon={UsersIcon} />
      ) : (
        <div id="users-table" className="cv-card overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-cv-border">
                <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">
                  Utilisateur
                </th>
                <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">
                  Email
                </th>
                <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">
                  {t('users.role')}
                </th>
                <th className="text-left px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">
                  Statut
                </th>
                <th className="text-right px-5 py-3 text-xs font-medium text-cv-muted uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr
                  key={user.id}
                  className={`border-b border-cv-border/50 hover:bg-cv-accent/5 transition-colors ${
                    user.isActive === false ? 'opacity-60' : ''
                  }`}
                >
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
                    <select
                      className="cv-input text-xs py-1 max-w-[140px]"
                      value={user.role}
                      disabled={busyId === user.id}
                      onChange={(e) => void changeRole(user.id, e.target.value as UserRole)}
                    >
                      {ROLE_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-5 py-4">
                    <span
                      className={`cv-badge border ${
                        user.isActive !== false
                          ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-400'
                          : 'border-red-400/30 bg-red-400/10 text-red-400'
                      }`}
                    >
                      <Shield className="w-3 h-3 inline mr-1" />
                      {user.isActive !== false ? 'Actif' : 'Désactivé'}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-right">
                    <button
                      type="button"
                      disabled={busyId === user.id}
                      onClick={() => void toggleActive(user.id, user.isActive !== false)}
                      className="cv-btn-ghost text-xs py-1"
                      title={user.isActive !== false ? 'Désactiver' : 'Réactiver'}
                    >
                      <UserX className="w-3.5 h-3.5" />
                      {user.isActive !== false ? 'Désactiver' : 'Réactiver'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
