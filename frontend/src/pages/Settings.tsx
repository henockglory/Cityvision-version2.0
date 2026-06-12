import { useTranslation } from 'react-i18next';
import { Globe, Bell, HardDrive, Shield } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import ThemeToggle from '@/components/ThemeToggle';
import MuteToggle from '@/components/MuteToggle';
import { useUiStore } from '@/stores/uiStore';
import { useSound } from '@/hooks/useSound';

export default function Settings() {
  const { t, i18n } = useTranslation();
  const theme = useUiStore((s) => s.theme);
  const soundMuted = useUiStore((s) => s.soundMuted);
  const { playClick } = useSound();

  const sections = [
    {
      title: t('settings.general'),
      icon: Shield,
      items: [
        { label: t('settings.language'), value: i18n.language.toUpperCase(), action: () => { playClick(); void i18n.changeLanguage(i18n.language === 'fr' ? 'en' : 'fr'); } },
        { label: t('settings.theme'), value: theme === 'dark' ? 'Sombre' : 'Clair', custom: <ThemeToggle /> },
      ],
    },
    {
      title: t('settings.notifications'),
      icon: Bell,
      items: [
        { label: 'Sons interface', value: soundMuted ? 'Désactivés' : 'Activés', custom: <MuteToggle /> },
        { label: 'Alertes email', value: 'Activé' },
        { label: 'Alertes push', value: 'Désactivé' },
      ],
    },
    {
      title: t('settings.storage'),
      icon: HardDrive,
      items: [
        { label: 'Rétention', value: '30 jours' },
        { label: 'Espace utilisé', value: '2.4 TB / 4 TB' },
        { label: 'Compression', value: 'H.265' },
      ],
    },
  ];

  return (
    <div>
      <PageHeader title={t('settings.title')} />

      <div className="space-y-6 max-w-2xl">
        {sections.map((section) => (
          <div key={section.title} className="cv-card p-5">
            <div className="flex items-center gap-2 mb-4">
              <section.icon className="w-5 h-5 text-cv-accent" />
              <h2 className="font-display text-lg font-semibold">{section.title}</h2>
            </div>
            <div className="space-y-3">
              {section.items.map((item) => (
                <div key={item.label} className="flex items-center justify-between py-2 border-b border-cv-border/50 last:border-0">
                  <span className="text-sm text-cv-muted">{item.label}</span>
                  {'custom' in item && item.custom ? (
                    item.custom
                  ) : 'action' in item && item.action ? (
                    <button type="button" onClick={item.action} className="cv-btn-ghost text-sm flex items-center gap-1">
                      <Globe className="w-3 h-3" />
                      {item.value}
                    </button>
                  ) : (
                    <span className="text-sm font-medium">{item.value}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
