import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Plus, Wifi, KeyRound, MonitorPlay, ChevronRight, ChevronLeft,
  Check, Loader2, MoreVertical, Camera as CameraIcon,
} from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import VideoPlaceholder from '@/components/ui/VideoPlaceholder';
import LoadingState from '@/components/ui/LoadingState';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import {
  useCameras,
  useCreateCamera,
  useDiscoverCameras,
  useTestCameraStream,
} from '@/hooks/api/queries';
import { useAuthStore } from '@/stores/authStore';
import { useSound } from '@/hooks/useSound';
import type { Camera, DiscoveredDevice } from '@/types';

type WizardStep = 1 | 2 | 3;

export default function Cameras() {
  const { t } = useTranslation();
  const { playClick, playSonar } = useSound();
  const siteId = useAuthStore((s) => s.siteId) ?? localStorage.getItem('cv_site_id');
  const { data: cameras = [], isLoading, isError, refetch } = useCameras();
  const discoverMutation = useDiscoverCameras();
  const createMutation = useCreateCamera();
  const testMutation = useTestCameraStream();

  const [showWizard, setShowWizard] = useState(false);
  const [step, setStep] = useState<WizardStep>(1);
  const [subnet, setSubnet] = useState('192.168.1.0/24');
  const [devices, setDevices] = useState<DiscoveredDevice[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<DiscoveredDevice | null>(null);
  const [credentials, setCredentials] = useState({ username: 'admin', password: '' });
  const [cameraName, setCameraName] = useState('');
  const [createdCameraId, setCreatedCameraId] = useState<string | null>(null);
  const [testOk, setTestOk] = useState(false);
  const [wizardError, setWizardError] = useState('');

  const handleScan = async () => {
    playSonar();
    setWizardError('');
    setDevices([]);
    setSelectedDevice(null);
    try {
      const { data } = await discoverMutation.mutateAsync(subnet);
      const list = Array.isArray(data) ? data : [];
      setDevices(list);
      if (list.length === 0) {
        setWizardError(t('cameras.wizard.noDevices'));
      }
    } catch {
      setWizardError(t('cameras.wizard.scanError'));
    }
  };

  const handleCreateAndTest = async () => {
    playClick();
    setWizardError('');
    setTestOk(false);
    if (!siteId || !selectedDevice) return;

    try {
      const name = cameraName.trim() || `Camera ${selectedDevice.ip}`;
      const { data } = await createMutation.mutateAsync({
        site_id: siteId,
        name,
        host: selectedDevice.ip,
        username: credentials.username,
        password: credentials.password,
        port: selectedDevice.rtsp_port ?? 554,
        vendor: 'generic',
      });
      const cam = data as Camera;
      setCreatedCameraId(cam.id);
      setCameraName(name);

      const testResult = await testMutation.mutateAsync(cam.id);
      if (testResult.data.reachable) {
        setTestOk(true);
        playSonar();
      } else {
        setWizardError(t('cameras.wizard.connectionFailed'));
      }
    } catch {
      setWizardError(t('cameras.wizard.createError'));
    }
  };

  const resetWizard = () => {
    setShowWizard(false);
    setStep(1);
    setDevices([]);
    setSelectedDevice(null);
    setCredentials({ username: 'admin', password: '' });
    setCameraName('');
    setCreatedCameraId(null);
    setTestOk(false);
    setWizardError('');
  };

  const statusBadge = (status: Camera['status']) => {
    const map = {
      online: 'cv-badge-online',
      offline: 'cv-badge-offline',
      recording: 'cv-badge-recording',
    };
    return <span className={map[status]}>{t(`cameras.status.${status}`)}</span>;
  };

  if (isLoading) return <LoadingState />;

  if (isError) {
    return (
      <div>
        <PageHeader title={t('cameras.title')} />
        <ErrorState onRetry={() => void refetch()} />
      </div>
    );
  }

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

          {wizardError && (
            <div className="max-w-lg mx-auto mb-4 px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm text-center">
              {wizardError}
            </div>
          )}

          {step === 1 && (
            <div className="max-w-lg mx-auto space-y-4">
              <div>
                <label className="cv-label">{t('cameras.wizard.subnet')}</label>
                <input value={subnet} onChange={(e) => setSubnet(e.target.value)} className="cv-input" />
              </div>
              <button
                type="button"
                onClick={() => void handleScan()}
                disabled={discoverMutation.isPending}
                className="cv-btn-primary w-full"
              >
                {discoverMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wifi className="w-4 h-4" />}
                {discoverMutation.isPending ? t('cameras.wizard.scanning') : t('cameras.wizard.scan')}
              </button>
              {devices.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm text-cv-muted">{t('cameras.wizard.selectDevice')}</p>
                  {devices.map((d) => (
                    <button
                      key={d.ip}
                      type="button"
                      onClick={() => { playClick(); setSelectedDevice(d); }}
                      className={`w-full flex items-center justify-between p-3 rounded-lg border transition-colors ${
                        selectedDevice?.ip === d.ip ? 'border-cv-accent bg-cv-accent/10' : 'border-cv-border hover:border-cv-accent/30'
                      }`}
                    >
                      <span className="font-mono text-sm">{d.ip}</span>
                      <span className="text-xs text-cv-muted">{d.vendor ?? d.model ?? (d.reachable ? 'reachable' : '')}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {step === 2 && selectedDevice && (
            <div className="max-w-lg mx-auto space-y-4">
              <p className="text-sm text-cv-muted text-center font-mono">{selectedDevice.ip}</p>
              <div>
                <label className="cv-label">{t('cameras.wizard.cameraName')}</label>
                <input
                  value={cameraName}
                  onChange={(e) => setCameraName(e.target.value)}
                  className="cv-input"
                  placeholder={`Camera ${selectedDevice.ip}`}
                />
              </div>
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
              <button
                type="button"
                onClick={() => void handleCreateAndTest()}
                disabled={createMutation.isPending || testMutation.isPending || !siteId}
                className="cv-btn-primary w-full"
              >
                {(createMutation.isPending || testMutation.isPending) ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <KeyRound className="w-4 h-4" />
                )}
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
              <VideoPlaceholder label={selectedDevice?.ip ?? cameraName} live={testOk} />
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
              disabled={
                (step === 1 && !selectedDevice) ||
                (step === 2 && !testOk) ||
                (step === 3 && !createdCameraId)
              }
              onClick={() => {
                playClick();
                if (step < 3) setStep((s) => (s + 1) as WizardStep);
                else { playSonar(); resetWizard(); void refetch(); }
              }}
              className="cv-btn-primary"
            >
              {step === 3 ? t('cameras.wizard.finish') : t('cameras.wizard.next')}
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {cameras.length === 0 ? (
        <EmptyState
          title={t('cameras.empty')}
          hint={t('cameras.emptyHint')}
          icon={CameraIcon}
          action={
            <button type="button" onClick={() => { playClick(); setShowWizard(true); }} className="cv-btn-primary">
              <Plus className="w-4 h-4" />
              {t('cameras.add')}
            </button>
          }
        />
      ) : (
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
      )}
    </div>
  );
}
