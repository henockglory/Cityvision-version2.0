import { useRef, useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { isAxiosError } from 'axios';
import {
  Plus, Wifi, KeyRound, MonitorPlay, ChevronRight, ChevronLeft,
  Check, Loader2, Camera as CameraIcon,
  AlertCircle, Info,
} from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import VideoPlaceholder from '@/components/ui/VideoPlaceholder';
import CameraCard from '@/components/camera/CameraCard';
import Go2RtcPlayer from '@/components/camera/Go2RtcPlayer';
import { go2rtcStreamSrc } from '@/config/streams';
import LoadingState from '@/components/ui/LoadingState';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import ConfirmDialog, { ToastStack } from '@/components/ui/ConfirmDialog';
import {
  useCameras,
  useCreateCamera,
  useDeleteCamera,
  useUpdateCamera,
  useDiscoverCameras,
  useTestCameraStream,
  useProbeCamera,
  useCameraPreview,
} from '@/hooks/api/queries';
import { useAuthStore } from '@/stores/authStore';
import { useSound } from '@/hooks/useSound';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';
import { useDialogTour } from '@/hooks/useDialogTour';
import DialogTourHelpButton from '@/components/ui/DialogTourHelpButton';
import type { Camera, DiscoveredDevice } from '@/types';

type WizardStep = 1 | 2 | 3 | 4;

function normalizeCameraHost(host: string): string {
  return host.split('/')[0].trim().toLowerCase();
}

export default function Cameras() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const startTour = useAutoPageTour('cameras');
  const siteId = useAuthStore((s) => s.siteId) ?? localStorage.getItem('cv_site_id');
  const orgId = useAuthStore((s) => s.orgId);
  const { data: cameras = [], isLoading, isError, refetch } = useCameras();
  const discoverMutation = useDiscoverCameras();
  const createMutation = useCreateCamera();
  const updateMutation = useUpdateCamera();
  const deleteMutation = useDeleteCamera();
  const testMutation = useTestCameraStream();
  const probeMutation = useProbeCamera();
  const previewMutation = useCameraPreview();

  const [showWizard, setShowWizard] = useState(false);
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [menuAnchorEl, setMenuAnchorEl] = useState<HTMLElement | null>(null);
  const menuAnchorRef = useRef<HTMLElement | null>(null);
  menuAnchorRef.current = menuAnchorEl;
  const [step, setStep] = useState<WizardStep>(1);
  const [subnet, setSubnet] = useState('192.168.1.0/24');
  const [devices, setDevices] = useState<DiscoveredDevice[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<DiscoveredDevice | null>(null);
  const [manualRtspUrl, setManualRtspUrl] = useState('');
  const [selectedVendor, setSelectedVendor] = useState<'auto' | 'hikvision' | 'dahua' | 'generic'>('auto');
  const [credentials, setCredentials] = useState({ username: 'admin', password: '' });
  const [cameraName, setCameraName] = useState('');
  const [createdCameraId, setCreatedCameraId] = useState<string | null>(null);
  const [testOk, setTestOk] = useState(false);
  const [detectedVendor, setDetectedVendor] = useState('generic');
  const [ffprobeInfo, setFfprobeInfo] = useState<{ video_codec?: string; width?: number; height?: number; fps?: number; error?: string; available?: boolean } | null>(null);
  const [previewOk, setPreviewOk] = useState(false);
  const [wizardError, setWizardError] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState<Camera | null>(null);
  const [testingStreamId, setTestingStreamId] = useState<string | null>(null);
  const [streamVersion, setStreamVersion] = useState<Record<string, number>>({});
  const [toasts, setToasts] = useState<Array<{ id: string; message: string }>>([]);

  const prepareWizardTourStep = useCallback((selector: string) => {
    const map: Record<string, WizardStep> = {
      '#camera-wizard-step1': 1,
      '#camera-wizard-step2': 2,
      '#camera-wizard-step3': 3,
      '#camera-wizard-step4': 4,
    };
    const n = map[selector];
    if (n) setStep(n);
  }, []);

  const startWizardTour = useDialogTour('cameraWizard', showWizard, { prepareStep: prepareWizardTourStep });

  useEffect(() => {
    if (deleteConfirm) {
      setMenuOpen(null);
      setMenuAnchorEl(null);
    }
  }, [deleteConfirm]);

  const pushToast = (message: string) => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { id, message }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4500);
  };

  const findExistingCameraId = (host: string): string | null => {
    const needle = normalizeCameraHost(host);
    const match = cameras.find((c) => normalizeCameraHost(c.ip) === needle);
    return createdCameraId ?? match?.id ?? null;
  };

  const handleScan = async () => {
    playClick();
    setWizardError('');
    setDevices([]);
    setSelectedDevice(null);
    const cidr = subnet.trim();
    if (!cidr) {
      setWizardError(t('cameras.wizard.scanInvalidCidr'));
      return;
    }
    try {
      const { data } = await discoverMutation.mutateAsync(cidr);
      const list = Array.isArray(data) ? data : [];
      list.sort((a, b) => {
        const score = (d: DiscoveredDevice) => (d.has_rtsp || d.rtsp_port ? 2 : 1);
        const diff = score(b) - score(a);
        return diff !== 0 ? diff : a.ip.localeCompare(b.ip);
      });
      setDevices(list);
      if (list.length === 0) {
        setWizardError(t('cameras.wizard.noDevices'));
      }
    } catch (err) {
      if (err instanceof Error && err.message === 'No organization') {
        setWizardError(t('cameras.wizard.scanAuthError'));
      } else if (isAxiosError(err) && err.code === 'ECONNABORTED') {
        setWizardError(t('cameras.wizard.scanTimeout'));
      } else if (isAxiosError(err) && err.response?.status === 429) {
        setWizardError(t('cameras.wizard.scanRateLimit'));
      } else if (isAxiosError(err) && err.response?.status === 400) {
        const msg = typeof err.response.data === 'object' && err.response.data && 'error' in err.response.data
          ? String((err.response.data as { error?: string }).error)
          : '';
        setWizardError(msg || t('cameras.wizard.scanInvalidCidr'));
      } else {
        setWizardError(t('cameras.wizard.scanError'));
      }
    }
  };

  const handleCreateAndTest = async () => {
    playClick();
    setWizardError('');
    setTestOk(false);
    setPreviewOk(false);

    const useManual = Boolean(manualRtspUrl.trim());
    const host = useManual
      ? manualRtspUrl.trim().replace(/^rtsp:\/\//, '').split('/')[0].split(':')[0]
      : selectedDevice?.ip ?? '';
    const port = useManual
      ? parseInt(manualRtspUrl.trim().replace(/^rtsp:\/\/[^:]+:/, '').split('/')[0]) || 554
      : selectedDevice?.rtsp_port ?? 554;
    const rtspPath = useManual
      ? '/' + manualRtspUrl.trim().split('/').slice(3).join('/')
      : undefined;

    if (!siteId || (!selectedDevice && !useManual)) {
      setWizardError(siteId ? t('cameras.wizard.noDevices') : t('cameras.wizard.missingSite'));
      return;
    }

    try {
      let vendor = selectedVendor === 'auto' ? 'generic' : selectedVendor;
      let detectedRtspPath = rtspPath;

      if (!useManual) {
        const probe = await probeMutation.mutateAsync({
          host,
          username: credentials.username,
          password: credentials.password,
          port,
          vendor: selectedVendor === 'auto' ? undefined : selectedVendor,
        });
        const best = probe.data.best;
        if (!best?.ok) {
          setWizardError(t('cameras.wizard.connectionFailed'));
          return;
        }
        vendor = (best.vendor as 'hikvision' | 'dahua' | 'generic') ?? vendor;
        detectedRtspPath = best.rtsp_path ?? detectedRtspPath;
        if ((probe.data as Record<string, unknown>).ffprobe) {
          setFfprobeInfo((probe.data as Record<string, unknown>).ffprobe as typeof ffprobeInfo);
        }
      }

      setDetectedVendor(vendor);
      const name = cameraName.trim() || (useManual ? `Camera ${host}` : `Camera ${host}`);
      const existingId = findExistingCameraId(host);
      const payload = {
        site_id: siteId,
        name,
        host,
        username: credentials.username,
        password: credentials.password,
        port,
        vendor,
        rtsp_path: detectedRtspPath,
        stream_profile: 'main' as const,
      };

      let cam: Camera;
      if (existingId && orgId) {
        const { data } = await updateMutation.mutateAsync({
          cameraId: existingId,
          body: {
            name: payload.name,
            host: payload.host,
            port: payload.port,
            username: payload.username,
            password: payload.password,
            vendor: payload.vendor,
            rtsp_path: payload.rtsp_path,
            stream_profile: payload.stream_profile,
          },
        });
        cam = data as Camera;
      } else {
        const { data } = await createMutation.mutateAsync(payload);
        cam = data as Camera;
      }
      setCreatedCameraId(cam.id);
      setCameraName(name);

      const testResult = await testMutation.mutateAsync(cam.id);
      if (testResult.data.video_ok) {
        setTestOk(true);
        playClick();
        try {
          await previewMutation.mutateAsync(cam.id);
          setPreviewOk(true);
          setStreamVersion((v) => ({ ...v, [cam.id]: (v[cam.id] ?? 0) + 1 }));
        } catch {
          setPreviewOk(false);
          setWizardError(t('cameras.wizard.previewFailed'));
        }
      } else {
        setWizardError(t('cameras.wizard.connectionFailed'));
      }
    } catch (err) {
      if (isAxiosError(err) && err.response?.status === 400) {
        const apiErr = typeof err.response.data === 'object' && err.response.data && 'error' in err.response.data
          ? String((err.response.data as { error?: string }).error)
          : '';
        if (apiErr.includes('site_id')) {
          setWizardError(t('cameras.wizard.missingSite'));
        } else {
          setWizardError(apiErr || t('cameras.wizard.createError'));
        }
      } else if (isAxiosError(err) && err.code === 'ECONNABORTED') {
        setWizardError(t('cameras.wizard.probeTimeout'));
      } else {
        setWizardError(t('cameras.wizard.createError'));
      }
    }
  };

  const handleTestStream = async (cam: Camera) => {
    if (!orgId || testingStreamId) return;
    playClick();
    setTestingStreamId(cam.id);
    try {
      await previewMutation.mutateAsync(cam.id);
      const testResult = await testMutation.mutateAsync(cam.id);
      if (testResult.data.video_ok) {
        pushToast(t('cameras.streamTestOk', { name: cam.name }));
        setStreamVersion((v) => ({ ...v, [cam.id]: (v[cam.id] ?? 0) + 1 }));
        void refetch();
      } else {
        pushToast(t('cameras.streamTestFailed', { name: cam.name }));
      }
    } catch {
      pushToast(t('cameras.streamTestFailed', { name: cam.name }));
    } finally {
      setTestingStreamId(null);
    }
  };

  const resetWizard = () => {
    setShowWizard(false);
    setStep(1);
    setDevices([]);
    setSelectedDevice(null);
    setManualRtspUrl('');
    setSelectedVendor('auto');
    setCredentials({ username: 'admin', password: '' });
    setCameraName('');
    setCreatedCameraId(null);
    setTestOk(false);
    setDetectedVendor('generic');
    setFfprobeInfo(null);
    setPreviewOk(false);
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
        <PageHeader title={t('cameras.title')} onHelpTour={startTour} />
        <ErrorState onRetry={() => void refetch()} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={t('cameras.title')}
        onHelpTour={startTour}
        actions={
          <button
            type="button"
            data-tour="add-camera"
            onClick={() => { playClick(); setShowWizard(true); }}
            className="cv-btn-primary"
          >
            <Plus className="w-4 h-4" />
            {t('cameras.add')}
          </button>
        }
      />

      {showWizard && (
        <div id="camera-wizard" className="cv-card p-6 mb-6 border-cv-accent/30 shadow-glow animate-fade-in">
          <div className="flex justify-end mb-2">
            <DialogTourHelpButton onClick={() => startWizardTour()} />
          </div>
          <div className="flex items-center justify-center gap-4 mb-8">
            {[
              { n: 1, label: t('cameras.wizard.step1'), icon: Wifi },
              { n: 2, label: t('cameras.wizard.step2'), icon: KeyRound },
              { n: 3, label: t('cameras.wizard.step3'), icon: MonitorPlay },
              { n: 4, label: t('cameras.wizard.step4', 'Aperçu'), icon: Check },
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
                {i < 3 && <ChevronRight className="w-4 h-4 text-cv-muted" />}
              </div>
            ))}
          </div>

          {wizardError && (
            <div className="max-w-lg mx-auto mb-4 px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm text-center">
              {wizardError}
            </div>
          )}

          {step === 1 && (
            <div id="camera-wizard-step1" className="max-w-lg mx-auto space-y-4">
              {/* Info honnête sur la couverture */}
              <div className="flex gap-2 p-3 rounded-lg bg-cv-surface border border-cv-border text-xs text-cv-muted">
                <Info className="w-3.5 h-3.5 shrink-0 mt-0.5 text-cv-accent" />
                <span>{t('cameras.wizard.scanHint')}</span>
              </div>

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
                      onClick={() => { playClick(); setSelectedDevice(d); setManualRtspUrl(''); }}
                      className={`w-full flex items-center justify-between p-3 rounded-lg border transition-colors ${
                        selectedDevice?.ip === d.ip ? 'border-cv-accent bg-cv-accent/10' : 'border-cv-border hover:border-cv-accent/30'
                      }`}
                    >
                      <span className="font-mono text-sm">{d.ip}</span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {(d.has_rtsp || d.rtsp_port) ? (
                          <span className="text-[10px] font-semibold uppercase tracking-wide text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-2 py-0.5 rounded-md">
                            RTSP{d.rtsp_port && d.rtsp_port !== 554 ? ` :${d.rtsp_port}` : ''}
                          </span>
                        ) : d.reachable ? (
                          <span className="text-[10px] font-medium uppercase tracking-wide text-cv-muted bg-cv-deep/60 border border-cv-border/50 px-2 py-0.5 rounded-md">
                            HTTP
                          </span>
                        ) : null}
                      </div>
                    </button>
                  ))}
                </div>
              )}

              {/* Séparateur + URL RTSP manuelle */}
              <div className="border-t border-cv-border/50 pt-3">
                <p className="text-xs font-medium text-cv-muted mb-2">{t('cameras.wizard.manualUrl')}</p>
                <p className="text-xs text-cv-muted mb-2">{t('cameras.wizard.manualUrlHint')}</p>
                <input
                  value={manualRtspUrl}
                  onChange={(e) => { setManualRtspUrl(e.target.value); if (e.target.value) setSelectedDevice(null); }}
                  placeholder={t('cameras.wizard.manualUrlPlaceholder')}
                  className="cv-input font-mono text-sm"
                />
              </div>

              {/* Sélecteur vendor */}
              <div>
                <label className="cv-label flex items-center gap-1">
                  {t('cameras.wizard.vendorLabel')}
                  <span className="text-xs text-cv-muted font-normal">({t('cameras.wizard.vendorHint')})</span>
                </label>
                <select
                  className="cv-input w-full"
                  value={selectedVendor}
                  onChange={(e) => setSelectedVendor(e.target.value as typeof selectedVendor)}
                >
                  {(['auto', 'hikvision', 'dahua', 'generic'] as const).map((v) => (
                    <option key={v} value={v}>{t(`cameras.wizard.vendor.${v}`)}</option>
                  ))}
                </select>
                {selectedVendor !== 'auto' && (
                  <p className={`text-xs mt-1 ${selectedVendor === 'generic' ? 'text-amber-400' : 'text-emerald-400'}`}>
                    {t(`cameras.wizard.vendorCoverage.${selectedVendor}`)}
                  </p>
                )}
              </div>

              {/* Aide générale */}
              <details className="text-xs text-cv-muted">
                <summary className="cursor-pointer flex items-center gap-1.5 text-cv-accent/80">
                  <AlertCircle className="w-3 h-3" />
                  {t('cameras.wizard.helpTitle')}
                </summary>
                <p className="mt-2 pl-4 border-l border-cv-border">{t('cameras.wizard.helpText')}</p>
              </details>
            </div>
          )}

          {step === 2 && (
            <div id="camera-wizard-step2" className="max-w-lg mx-auto space-y-4">
              {(selectedDevice || manualRtspUrl.trim()) ? (
              <>
              <p className="text-sm text-cv-muted text-center font-mono">
                {selectedDevice?.ip ?? manualRtspUrl.trim().replace(/^rtsp:\/\//, '').split('/')[0]}
              </p>
              <div>
                <label className="cv-label">{t('cameras.wizard.cameraName')}</label>
                <input
                  value={cameraName}
                  onChange={(e) => setCameraName(e.target.value)}
                  className="cv-input"
                  placeholder={selectedDevice ? `Camera ${selectedDevice.ip}` : t('cameras.wizard.cameraName')}
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
                disabled={
                  createMutation.isPending ||
                  updateMutation.isPending ||
                  testMutation.isPending ||
                  previewMutation.isPending ||
                  !siteId
                }
                className="cv-btn-primary w-full"
              >
                {(createMutation.isPending || updateMutation.isPending || testMutation.isPending || previewMutation.isPending) ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <KeyRound className="w-4 h-4" />
                )}
                {findExistingCameraId(
                  selectedDevice?.ip ??
                    manualRtspUrl.trim().replace(/^rtsp:\/\//, '').split('/')[0].split(':')[0],
                )
                  ? t('cameras.wizard.retryConnection')
                  : t('cameras.wizard.testConnection')}
              </button>
              {testOk && (
                <div className="space-y-2">
                  <div className="flex items-center justify-center gap-2 text-emerald-400 text-sm">
                    <Check className="w-4 h-4" /> {t('cameras.wizard.connectionSuccess')}
                  </div>
                  <p className="text-xs text-center text-cv-muted">
                    {t('cameras.wizard.detectedVendor', 'Profil détecté')}: <span className="font-mono text-cv-accent">{detectedVendor}</span>
                  </p>
                  {ffprobeInfo?.video_codec && (
                    <p className="text-xs text-center text-emerald-400/80">
                      {ffprobeInfo.video_codec.toUpperCase()}
                      {ffprobeInfo.width ? ` · ${ffprobeInfo.width}×${ffprobeInfo.height}` : ''}
                      {ffprobeInfo.fps ? ` · ${ffprobeInfo.fps} fps` : ''}
                    </p>
                  )}
                  {ffprobeInfo?.available && ffprobeInfo.error && (
                    <p className="text-xs text-center text-amber-400">
                      {t('cameras.wizard.ffprobeWarn')}: {ffprobeInfo.error}
                    </p>
                  )}
                  {ffprobeInfo && !ffprobeInfo.available && (
                    <p className="text-xs text-center text-cv-muted/60">
                      {t('cameras.wizard.ffprobeNotInstalled', 'Validation approfondie indisponible (ffprobe absent)')}
                    </p>
                  )}
                </div>
              )}
              </>
              ) : (
                <p className="text-sm text-cv-muted text-center">{t('cameras.wizard.selectDevice')}</p>
              )}
            </div>
          )}

          {step === 3 && (
            <div id="camera-wizard-step3" className="max-w-2xl mx-auto text-center space-y-4">
              <p className="text-sm text-cv-muted">{t('cameras.wizard.validating', 'Vérification de la connexion…')}</p>
              {testOk ? (
                <div className="flex items-center justify-center gap-2 text-emerald-400">
                  <Check className="w-5 h-5" /> {cameraName}
                </div>
              ) : wizardError ? (
                <div className="flex items-center justify-center gap-2 text-red-400 text-sm">
                  <AlertCircle className="w-5 h-5" />
                  {t('cameras.wizard.connectionFailed')}
                  <button type="button" className="cv-btn-secondary text-xs ml-2" onClick={() => setStep(2)}>
                    {t('cameras.wizard.back')}
                  </button>
                </div>
              ) : (
                <Loader2 className="w-6 h-6 animate-spin mx-auto text-cv-accent" />
              )}
            </div>
          )}

          {step === 4 && (
            <div id="camera-wizard-step4" className="max-w-3xl mx-auto">
              <p className="text-sm text-cv-muted text-center mb-4">{t('cameras.wizard.preview')}</p>
              {previewOk && createdCameraId ? (
                <Go2RtcPlayer
                  className="aspect-video w-full rounded-xl border border-cv-border"
                  src={go2rtcStreamSrc({ id: createdCameraId }) ?? undefined}
                  label={cameraName}
                />
              ) : (
                <VideoPlaceholder label={selectedDevice?.ip ?? cameraName} live={false} />
              )}
              {!previewOk && testOk && (
                <p className="text-sm text-red-400 text-center mt-3">{t('cameras.wizard.previewFailed')}</p>
              )}
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
                (step === 1 && !selectedDevice && !manualRtspUrl.trim()) ||
                (step === 2 && !testOk) ||
                (step === 3 && !createdCameraId) ||
                (step === 4 && !previewOk)
              }
              onClick={() => {
                playClick();
                if (step < 4) {
                  if (step === 2 && !testOk) return;
                  setStep((s) => (s + 1) as WizardStep);
                } else {
                  playClick();
                  resetWizard();
                  void refetch();
                }
              }}
              className="cv-btn-primary"
            >
              {step === 4 ? t('cameras.wizard.finish') : t('cameras.wizard.next')}
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {!showWizard && cameras.length === 0 ? (
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
      ) : !showWizard ? (
        <div id="cameras-list" className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {cameras.map((cam) => (
            <CameraCard
              key={`${cam.id}-${streamVersion[cam.id] ?? 0}`}
              camera={cam}
              menuOpen={menuOpen === cam.id}
              menuAnchorRef={menuAnchorRef}
              menuAnchorEl={menuAnchorEl}
              onMenuToggle={(el) => {
                if (el) {
                  setMenuOpen(cam.id);
                  setMenuAnchorEl(el);
                } else {
                  setMenuOpen(null);
                  setMenuAnchorEl(null);
                }
              }}
              onMenuClose={() => { setMenuOpen(null); setMenuAnchorEl(null); }}
              onDelete={() => {
                setMenuOpen(null);
                setMenuAnchorEl(null);
                playClick();
                setDeleteConfirm(cam);
              }}
              onTestStream={() => void handleTestStream(cam)}
              testingStream={testingStreamId === cam.id}
              statusBadge={statusBadge(cam.status)}
            />
          ))}
        </div>
      ) : null}
      <ConfirmDialog
        open={deleteConfirm != null}
        title={t('cameras.deleteConfirmTitle')}
        message={t('cameras.deleteConfirmMessage', { name: deleteConfirm?.name ?? '' })}
        detail={deleteConfirm?.ip}
        confirmLabel={t('cameras.delete')}
        danger
        loading={deleteMutation.isPending}
        loadingLabel={t('cameras.deleting')}
        onCancel={() => {
          if (deleteMutation.isPending) return;
          setDeleteConfirm(null);
        }}
        onConfirm={() => {
          const camera = deleteConfirm;
          if (!camera?.id || deleteMutation.isPending) return;
          deleteMutation.mutate(camera.id, {
            onSuccess: () => {
              setDeleteConfirm(null);
              pushToast(t('cameras.deleteSuccess', { name: camera.name }));
            },
            onError: (err) => {
              if (err instanceof Error && err.message === 'No organization') {
                pushToast(t('cameras.wizard.scanAuthError'));
                return;
              }
              const detail =
                isAxiosError(err) && typeof err.response?.data === 'object' && err.response.data !== null
                  ? String((err.response.data as { error?: string }).error ?? '')
                  : '';
              pushToast(
                detail
                  ? `${t('cameras.deleteFailed', { name: camera.name })} (${detail})`
                  : t('cameras.deleteFailed', { name: camera.name }),
              );
            },
          });
        }}
      />
      <ToastStack toasts={toasts} />
    </div>
  );
}
