import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Plus, Wifi, KeyRound, MonitorPlay, ChevronRight, ChevronLeft,
  Check, Loader2, MoreVertical,
} from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import VideoPlaceholder from '@/components/ui/VideoPlaceholder';
import LoadingState from '@/components/ui/LoadingState';
import { mockScanDevices } from '@/data/mock';
import { useCameras } from '@/hooks/api/queries';
import { useSound } from '@/hooks/useSound';
import type { Camera } from '@/types';

type WizardStep = 1 | 2 | 3;

export default function Cameras() {
  const { t } = useTranslation();
  const { playClick, playSonar } = useSound();
  const { data: cameras = [], isLoading } = useCameras();
  const [showWizard, setShowWizard] = useState(false);
  const [step, setStep] = useState<WizardStep>(1);
  const [subnet, setSubnet] = useState('192.168.1.0/24');
  const [scanning, setScanning] = useState(false);
  const [devices, setDevices] = useState<{ ip: string; model?: string }[]>([]);
  const [selectedIp, setSelectedIp] = useState('');
  const [credentials, setCredentials] = useState({ username: 'admin', password: '' });
  const [testOk, setTestOk] = useState(false);
  const [testing, setTesting] = useState(false);

  const handleScan = async () => {
    playSonar();
    setScanning(true);
    setDevices([]);
    await new Promise((r) => setTimeout(r, 2000));
    setDevices(mockScanDevices);
    setScanning(false);
  };

  const handleTest = async () => {
    playClick();
    setTesting(true);
    await new Promise((r) => setTimeout(r, 1500));
    setTestOk(true);
    setTesting(false);
    playSonar();
  };

  const resetWizard = () => {
    setShowWizard(false);
    setStep(1);
    setDevices([]);
    setSelectedIp('');
    setCredentials({ username: 'admin', password: '' });
    setTestOk(false);
  };

  const statusBadge = (status: Camera['status']) => {
    const map = {
      online: 'cv-badge-online',
      offline: 'cv-badge-offline',
      recording: 'cv-badge-recording',
    };
    return (
      <span className={map[status]}>{t(`cameras.status.${status}`)}</span>
    );
  };

  if (isLoading) return <LoadingState />;

  return (
    <div>
      <PageHeader
        title={t('cameras.title')}
        actions={
          <button
            type="button"
            onClick={() => { playClick(); setShowWizard(true); }}
            className="cv-btn-primary"
          >
            <Plus className="w-4 h-4" />
            {t('cameras.add')}
          </button>
        }
      />

      {showWizard && (
        <div className="cv-card p-6 mb-6 border-cv-accent/30 shadow-glow animate-fade-in">
          <div className="flex items-center justify-center gap-4 mb-8">
            {[
              { n: 1, label: t('cameras.wizard.step1'), icon: Wifi },
              { n: 2, label: t('cameras.wizard.step2'), icon: KeyRound },
              { n: 3, label: t('cameras.wizard.step3'), icon: MonitorPlay },
            ].map((s, i) => (
              <div key={s.n} className="flex items-center gap-2">
                <div className={`flex items-center gap-2 px-4 py-2 rounded-lg border ${
                  step === s.n ? 'border-cv-accent bg-cv-accent/10 text-cv-accent' :
                  step > s.n ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400' :
                  'border-cv-border text-cv-muted'
                }`}>
                  {step > s.n ? <Check className="w-4 h-4" /> : <s.icon className="w-4 h-4" />}
                  <span className="text-sm font-medium hidden sm:inline">{s.label}</span>
                </div>
                {i < 2 && <ChevronRight className="w-4 h-4 text-cv-muted" />}
              </div>
            ))}
          </div>

          {step === 1 && (
            <div className="max-w-lg mx-auto space-y-4">
              <div>
                <label className="cv-label">{t('cameras.wizard.subnet')}</label>
                <input value={subnet} onChange={(e) => setSubnet(e.target.value)} className="cv-input" />
              </div>
              <button type="button" onClick={handleScan} disabled={scanning} className="cv-btn-primary w-full">
                {scanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wifi className="w-4 h-4" />}
                {scanning ? t('cameras.wizard.scanning') : t('cameras.wizard.scan')}
              </button>
              {devices.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm text-cv-muted">{t('cameras.wizard.selectDevice')}</p>
                  {devices.map((d) => (
                    <button
                      key={d.ip}
                      type="button"
                      onClick={() => { playClick(); setSelectedIp(d.ip); }}
                      className={`w-full flex items-center justify-between p-3 rounded-lg border transition-colors ${
                        selectedIp === d.ip ? 'border-cv-accent bg-cv-accent/10' : 'border-cv-border hover:border-cv-accent/30'
                      }`}
                    >
                      <span className="font-mono text-sm">{d.ip}</span>
                      <span className="text-xs text-cv-muted">{d.model}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {step === 2 && (
            <div className="max-w-lg mx-auto space-y-4">
              <p className="text-sm text-cv-muted text-center font-mono">{selectedIp}</p>
              <div>
                <label className="cv-label">{t('cameras.wizard.username')}</label>
                <input
                  value={credentials.username}
                  onChange={(e) => setCredentials({ ...credentials, username: e.target.value })}
                  className="cv-input"
                />
              </div>
              <div>
                <label className="cv-label">{t('cameras.wizard.password')}</label>
                <input
                  type="password"
                  value={credentials.password}
                  onChange={(e) => setCredentials({ ...credentials, password: e.target.value })}
                  className="cv-input"
                />
              </div>
              <button type="button" onClick={handleTest} disabled={testing} className="cv-btn-primary w-full">
                {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />}
                {t('cameras.wizard.testConnection')}
              </button>
              {testOk && (
                <div className="flex items-center justify-center gap-2 text-emerald-400 text-sm">
                  <Check className="w-4 h-4" /> {t('cameras.wizard.connectionSuccess')}
                </div>
              )}
            </div>
          )}

          {step === 3 && (
            <div className="max-w-2xl mx-auto">
              <p className="text-sm text-cv-muted text-center mb-4">{t('cameras.wizard.preview')}</p>
              <VideoPlaceholder label={selectedIp} />
            </div>
          )}

          <div className="flex justify-between mt-8 max-w-lg mx-auto">
            <button
              type="button"
              onClick={() => { playClick(); step === 1 ? resetWizard() : setStep((s) => (s - 1) as WizardStep); }}
              className="cv-btn-secondary"
            >
              <ChevronLeft className="w-4 h-4" />
              {step === 1 ? t('common.cancel') : t('cameras.wizard.back')}
            </button>
            <button
              type="button"
              disabled={(step === 1 && !selectedIp) || (step === 2 && !testOk)}
              onClick={() => {
                playClick();
                if (step < 3) setStep((s) => (s + 1) as WizardStep);
                else { playSonar(); resetWizard(); }
              }}
              className="cv-btn-primary"
            >
              {step === 3 ? t('cameras.wizard.finish') : t('cameras.wizard.next')}
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {cameras.map((cam) => (
          <div key={cam.id} className="cv-card-hover overflow-hidden">
            <VideoPlaceholder label={cam.name} live={cam.status !== 'offline'} className="rounded-none rounded-t-xl" />
            <div className="p-4">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-medium">{cam.name}</h3>
                  <p className="text-xs text-cv-muted font-mono mt-0.5">{cam.ip}</p>
                </div>
                <button type="button" className="text-cv-muted hover:text-cv-accent p-1">
                  <MoreVertical className="w-4 h-4" />
                </button>
              </div>
              <div className="flex items-center justify-between mt-3">
                <span className="text-xs text-cv-muted">{cam.location}</span>
                {statusBadge(cam.status)}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
