import { useEffect, useState, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Shield, Bell, UserSearch, User, Building2, Lock, Mail, Sparkles, Palette, Film, Route, HardDrive,
} from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import ThemeToggle from '@/components/ThemeToggle';
import MuteToggle from '@/components/MuteToggle';
import SurveillanceListsPanel from '@/components/settings/SurveillanceListsPanel';
import EvidenceDefaultsPanel from '@/components/settings/EvidenceDefaultsPanel';
import AlertRoutingPanel from '@/components/settings/AlertRoutingPanel';
import SystemPanel from '@/components/settings/SystemPanel';
import InfoTip from '@/components/ui/InfoTip';
import ConfirmDialog from '@/components/ui/ConfirmDialog';
import { authApi, orgApi, type OrganizationSettings } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import { useUiStore } from '@/stores/uiStore';
import { useSound } from '@/hooks/useSound';
import { useAutoPageTour, useRunTour } from '@/hooks/useAutoPageTour';
import { TOUR_LABELS, type TourId } from '@/lib/tourRegistry';

type Tab = 'general' | 'profile' | 'org' | 'security' | 'notifications' | 'integrations' | 'identity' | 'evidence' | 'routing' | 'system' | 'demo';

const TABS: { id: Tab; label: string; icon: typeof Shield }[] = [
  { id: 'general', label: 'Général', icon: Palette },
  { id: 'profile', label: 'Profil', icon: User },
  { id: 'org', label: 'Organisation', icon: Building2 },
  { id: 'security', label: 'Sécurité', icon: Lock },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'integrations', label: 'Intégrations', icon: Mail },
  { id: 'evidence', label: 'Preuves & capture', icon: Film },
  { id: 'routing', label: 'Routage alertes', icon: Route },
  { id: 'identity', label: 'Identité', icon: UserSearch },
  { id: 'system', label: 'Système', icon: HardDrive },
  { id: 'demo', label: 'Démo', icon: Sparkles },
];

export default function Settings() {
  const { t, i18n } = useTranslation();
  const orgId = useAuthStore((s) => s.orgId);
  const user = useAuthStore((s) => s.user);
  const theme = useUiStore((s) => s.theme);
  const tooltipsEnabled = useUiStore((s) => s.tooltipsEnabled);
  const soundUiEnabled = useUiStore((s) => s.soundUiEnabled);
  const soundAlertsEnabled = useUiStore((s) => s.soundAlertsEnabled);
  const networkEffectEnabled = useUiStore((s) => s.networkEffectEnabled);
  const toggleTooltips = useUiStore((s) => s.toggleTooltips);
  const toggleSoundUi = useUiStore((s) => s.toggleSoundUi);
  const toggleSoundAlerts = useUiStore((s) => s.toggleSoundAlerts);
  const toggleNetworkEffect = useUiStore((s) => s.toggleNetworkEffect);
  const toggleToursAutoStart = useUiStore((s) => s.toggleToursAutoStart);
  const resetAllTours = useUiStore((s) => s.resetAllTours);
  const toursAutoStart = useUiStore((s) => s.toursAutoStart);
  const { playClick } = useSound();
  const runTour = useRunTour();
  const startSettingsTour = useAutoPageTour('settings');
  const [tab, setTab] = useState<Tab>('general');
  const [org, setOrg] = useState<OrganizationSettings | null>(null);
  const [profileName, setProfileName] = useState(user?.username ?? '');
  const [profileEmail, setProfileEmail] = useState(user?.email ?? '');
  const [newPassword, setNewPassword] = useState('');
  const [smtpTo, setSmtpTo] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [totpSecret, setTotpSecret] = useState('');
  const [msg, setMsg] = useState('');
  const [confirmReset, setConfirmReset] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const st = location.state as { tab?: Tab } | null;
    if (st?.tab) setTab(st.tab);
  }, [location.state]);

  useEffect(() => {
    if (!orgId) return;
    void orgApi.get(orgId).then((r) => setOrg(r.data)).catch(() => undefined);
  }, [orgId]);

  const saveProfile = async () => {
    if (!orgId) return;
    playClick();
    await authApi.updateMe({
      full_name: profileName,
      email: profileEmail,
      ...(newPassword ? { password: newPassword } : {}),
      locale: i18n.language,
    });
    setNewPassword('');
    setMsg('Profil enregistré.');
  };

  const saveOrg = async () => {
    if (!orgId || !org) return;
    playClick();
    const r = await orgApi.update(orgId, {
      name: org.name,
      timezone: org.timezone,
      smtp_config: org.smtp_config,
      security_prefs: org.security_prefs,
      notification_prefs: org.notification_prefs,
    });
    setOrg(r.data);
    setMsg('Organisation enregistrée.');
  };

  const testSmtp = async () => {
    if (!orgId || !smtpTo) return;
    playClick();
    await orgApi.testSmtp(orgId, smtpTo);
    setMsg('Email de test envoyé.');
  };

  const setupTotp = async () => {
    playClick();
    const r = await authApi.setupTotp();
    setTotpSecret(r.data.secret);
    setMsg('Scannez le secret dans votre app 2FA, puis confirmez.');
  };

  const confirmTotp = async () => {
    playClick();
    await authApi.confirmTotp(totpCode);
    setMsg('2FA activée.');
    setTotpSecret('');
  };

  const resetDemo = async () => {
    if (!orgId) return;
    playClick();
    await orgApi.resetDemo(orgId);
    setConfirmReset(false);
    setMsg('Données démo réinitialisées (règles seed et listes).');
  };

  return (
    <div>
      <PageHeader title={t('settings.title')} onHelpTour={startSettingsTour} />
      {msg && (
        <p className="mb-4 text-sm text-cv-accent bg-cv-accent/10 border border-cv-accent/20 rounded-lg px-4 py-2">
          {msg}
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-6">
        <nav id="settings-tabs" className="cv-card p-3 space-y-1 h-fit">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => { playClick(); setTab(id); }}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                tab === id ? 'bg-cv-accent/15 text-cv-accent' : 'text-cv-muted hover:text-cv-text'
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </nav>

        <div className="space-y-6">
          {tab === 'general' && (
            <Section title="Général" icon={Palette}>
              <Row label={t('settings.language')} custom={
                <button type="button" className="cv-btn-secondary text-xs" onClick={() => void i18n.changeLanguage(i18n.language === 'fr' ? 'en' : 'fr')}>
                  {i18n.language.toUpperCase()}
                </button>
              } />
              <Row label={t('settings.theme')} value={theme === 'dark' ? 'Sombre' : 'Clair'} custom={<ThemeToggle />} />
              <Row label="Aide contextuelle" custom={
                <button type="button" className="cv-btn-secondary text-xs" onClick={toggleTooltips}>
                  {tooltipsEnabled ? 'Activée' : 'Désactivée'}
                </button>
              } />
              <Row label="Effet réseau (fond)" custom={
                <button type="button" className="cv-btn-secondary text-xs" onClick={toggleNetworkEffect}>
                  {networkEffectEnabled ? 'Activé' : 'Désactivé'}
                </button>
              } />
              <Row label="Sons interface (clics)" custom={
                <button type="button" className="cv-btn-secondary text-xs" onClick={toggleSoundUi}>
                  {soundUiEnabled ? 'Activés' : 'Désactivés'}
                </button>
              } />
              <Row label="Sons alertes" custom={
                <button type="button" className="cv-btn-secondary text-xs" onClick={toggleSoundAlerts}>
                  {soundAlertsEnabled ? 'Activés' : 'Désactivés'}
                </button>
              } />
              <Row label={t('settings.sound')} custom={<MuteToggle />} />
              <div className="border-t border-cv-border pt-4 mt-2">
                <p className="text-sm font-medium mb-2">{t('settings.toursTitle')}</p>
                <Row
                  label={t('settings.toursAutoStart')}
                  custom={
                    <button type="button" onClick={() => { playClick(); toggleToursAutoStart(); }} className="cv-btn-secondary text-xs">
                      {toursAutoStart ? t('settings.toursAutoOn') : t('settings.toursAutoOff')}
                    </button>
                  }
                />
                <div className="flex flex-wrap gap-2 mt-2">
                  {(Object.keys(TOUR_LABELS) as TourId[]).filter((id) => id !== 'global').map((id) => (
                    <button
                      key={id}
                      type="button"
                      className="cv-btn-secondary text-xs"
                      onClick={() => { playClick(); runTour(id); }}
                    >
                      {t(TOUR_LABELS[id])}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  className="cv-btn-ghost text-xs mt-2"
                  onClick={() => { playClick(); resetAllTours(); useUiStore.setState({ onboardingCompleted: false }); }}
                >
                  {t('settings.resetAllTours')}
                </button>
              </div>
            </Section>
          )}

          {tab === 'profile' && (
            <Section title="Profil utilisateur" icon={User}>
              <Field label="Nom complet" value={profileName} onChange={setProfileName} />
              <Field label="Email" value={profileEmail} onChange={setProfileEmail} type="email" />
              <Field label="Nouveau mot de passe" value={newPassword} onChange={setNewPassword} type="password" hint="Laisser vide pour ne pas changer" />
              <button type="button" onClick={() => void saveProfile()} className="cv-btn-primary">Enregistrer</button>
            </Section>
          )}

          {tab === 'org' && org && (
            <Section title="Organisation" icon={Building2}>
              <Field label="Nom" value={org.name} onChange={(v) => setOrg({ ...org, name: v })} />
              <Field label="Fuseau horaire" value={org.timezone} onChange={(v) => setOrg({ ...org, timezone: v })} />
              <div>
                <label className="cv-label">Profil de déploiement</label>
                <p className="text-[11px] text-cv-muted mb-1">Utilisé pour personnaliser le catalogue des règles.</p>
                <select
                  className="cv-input"
                  value={String((org.notification_prefs as Record<string, unknown> | undefined)?.deployment_profile ?? 'enterprise')}
                  onChange={(e) => {
                    const v = e.target.value;
                    setOrg({
                      ...org,
                      notification_prefs: { ...(org.notification_prefs ?? {}), deployment_profile: v },
                    });
                  }}
                >
                  <option value="national">Nationale</option>
                  <option value="enterprise">Entreprise</option>
                  <option value="domestic">Domestique</option>
                </select>
              </div>
              <button type="button" onClick={() => void saveOrg()} className="cv-btn-primary">Enregistrer</button>
            </Section>
          )}

          {tab === 'security' && org && (
            <Section title="Sécurité" icon={Lock}>
              <Field
                label="Longueur min. mot de passe"
                value={String((org.security_prefs as Record<string, number>)?.min_password_length ?? 12)}
                onChange={(v) => setOrg({
                  ...org,
                  security_prefs: { ...org.security_prefs, min_password_length: Number(v) },
                })}
                type="number"
              />
              <Row label="Exiger 2FA pour admins" custom={
                <button
                  type="button"
                  className="cv-btn-secondary text-xs"
                  onClick={() => setOrg({
                    ...org,
                    security_prefs: {
                      ...org.security_prefs,
                      require_2fa_admins: !(org.security_prefs as Record<string, boolean>)?.require_2fa_admins,
                    },
                  })}
                >
                  {(org.security_prefs as Record<string, boolean>)?.require_2fa_admins ? 'Oui' : 'Non'}
                </button>
              } />
              <div className="border-t border-cv-border pt-4 mt-4">
                <p className="text-sm font-medium mb-2 flex items-center gap-1">
                  Authentification à deux facteurs
                  <InfoTip content="Protège votre compte avec un code TOTP (Google Authenticator, etc.)" />
                </p>
                {totpSecret && <p className="text-xs font-mono bg-cv-deep/50 p-2 rounded mb-2 break-all">{totpSecret}</p>}
                <div className="flex gap-2 flex-wrap">
                  <button type="button" onClick={() => void setupTotp()} className="cv-btn-secondary text-xs">Configurer 2FA</button>
                  <input className="cv-input max-w-[120px] text-sm" placeholder="Code" value={totpCode} onChange={(e) => setTotpCode(e.target.value)} />
                  <button type="button" onClick={() => void confirmTotp()} className="cv-btn-primary text-xs">Confirmer</button>
                </div>
              </div>
              <button type="button" onClick={() => void saveOrg()} className="cv-btn-primary mt-4">Enregistrer politique</button>
            </Section>
          )}

          {tab === 'notifications' && (
            <Section title="Notifications" icon={Bell}>
              <Row label={t('settings.sound')} custom={<MuteToggle />} />
            </Section>
          )}

          {tab === 'integrations' && org && (
            <Section title="Email (SMTP)" icon={Mail}>
              <Field label="Hôte" value={org.smtp_config?.host ?? ''} onChange={(v) => setOrg({ ...org, smtp_config: { ...org.smtp_config, host: v } })} />
              <Field label="Port" value={String(org.smtp_config?.port ?? 587)} onChange={(v) => setOrg({ ...org, smtp_config: { ...org.smtp_config, port: Number(v) } })} type="number" />
              <Field label="Utilisateur" value={org.smtp_config?.user ?? ''} onChange={(v) => setOrg({ ...org, smtp_config: { ...org.smtp_config, user: v } })} />
              <Field label="Mot de passe" value={org.smtp_config?.password ?? ''} onChange={(v) => setOrg({ ...org, smtp_config: { ...org.smtp_config, password: v } })} type="password" />
              <Field label="Expéditeur" value={org.smtp_config?.from_address ?? ''} onChange={(v) => setOrg({ ...org, smtp_config: { ...org.smtp_config, from_address: v } })} />
              <div className="border-t border-cv-border pt-4 mt-2">
                <p className="text-sm font-medium mb-2">Notifications par défaut (org)</p>
                <Field
                  label="E-mail alertes par défaut"
                  value={String((org.notification_prefs as Record<string, string>)?.default_email ?? '')}
                  onChange={(v) => setOrg({
                    ...org,
                    notification_prefs: { ...org.notification_prefs, default_email: v },
                  })}
                />
                <Field
                  label="Webhook par défaut"
                  value={String((org.notification_prefs as Record<string, string>)?.default_webhook_url ?? '')}
                  onChange={(v) => setOrg({
                    ...org,
                    notification_prefs: { ...org.notification_prefs, default_webhook_url: v },
                  })}
                />
              </div>
              <div className="flex gap-2 flex-wrap items-end">
                <Field label="Email test" value={smtpTo} onChange={setSmtpTo} type="email" />
                <button type="button" onClick={() => void testSmtp()} className="cv-btn-secondary">Tester</button>
                <button type="button" onClick={() => void saveOrg()} className="cv-btn-primary">Enregistrer SMTP</button>
              </div>
            </Section>
          )}

          {tab === 'evidence' && (
            <Section title="Preuves & capture" icon={Film}>
              <EvidenceDefaultsPanel />
            </Section>
          )}

          {tab === 'routing' && (
            <Section title="Routage des alertes" icon={Route}>
              <AlertRoutingPanel />
            </Section>
          )}

          {tab === 'identity' && (
            <Section title="Listes de surveillance" icon={UserSearch}>
              <SurveillanceListsPanel />
            </Section>
          )}

          {tab === 'system' && (
            <Section title="Système" icon={HardDrive}>
              <SystemPanel />
            </Section>
          )}

          {tab === 'demo' && (
            <Section title="Environnement démo" icon={Sparkles}>
              <p className="text-sm text-cv-muted mb-4">
                Les données de démonstration (règles seed, listes) sont identifiables par le bandeau « Mode démo ».
                La caméra virtuelle et la vidéo ne sont pas supprimées.
              </p>
              <button type="button" onClick={() => setConfirmReset(true)} className="cv-btn-danger">
                Réinitialiser les données démo
              </button>
            </Section>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirmReset}
        title="Réinitialiser la démo ?"
        message="Supprime les règles activées depuis le catalogue et les listes de surveillance. Irréversible."
        confirmLabel="Réinitialiser"
        danger
        onConfirm={() => void resetDemo()}
        onCancel={() => setConfirmReset(false)}
      />
    </div>
  );
}

function Section({ title, icon: Icon, children }: { title: string; icon: typeof Shield; children: ReactNode }) {
  return (
    <div className="cv-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Icon className="w-5 h-5 text-cv-accent" />
        <h2 className="font-display text-lg font-semibold">{title}</h2>
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  );
}

function Row({ label, value, action, custom }: { label: string; value?: string; action?: () => void; custom?: ReactNode }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-cv-border/50 last:border-0">
      <span className="text-sm text-cv-muted">{label}</span>
      {custom ?? (action ? (
        <button type="button" onClick={action} className="cv-btn-secondary text-xs">{value}</button>
      ) : (
        <span className="text-sm font-medium">{value}</span>
      ))}
    </div>
  );
}

function Field({
  label, value, onChange, type = 'text', hint,
}: {
  label: string; value: string; onChange: (v: string) => void; type?: string; hint?: string;
}) {
  return (
    <div>
      <label className="cv-label">{label}</label>
      {hint && <p className="text-[11px] text-cv-muted mb-1">{hint}</p>}
      <input type={type} className="cv-input" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
