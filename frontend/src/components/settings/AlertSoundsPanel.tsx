import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Play, Trash2, Upload } from 'lucide-react';
import { ALERT_SOUND_CATALOG, DEFAULT_ALERT_SOUND_ID } from '@/lib/alertSounds';
import {
  addCustomAlertSound,
  deleteCustomAlertSound,
  listCustomAlertSounds,
  type CustomAlertSoundMeta,
} from '@/lib/customAlertSounds';
import { useSound } from '@/hooks/useSound';
import { useUiStore } from '@/stores/uiStore';

export default function AlertSoundsPanel() {
  const { t, i18n } = useTranslation();
  const isEn = i18n.language.startsWith('en');
  const alertSoundId = useUiStore((s) => s.alertSoundId);
  const alertSoundVolume = useUiStore((s) => s.alertSoundVolume);
  const setAlertSoundId = useUiStore((s) => s.setAlertSoundId);
  const setAlertSoundVolume = useUiStore((s) => s.setAlertSoundVolume);
  const { playAlertTone, playClick } = useSound();
  const [customs, setCustoms] = useState<CustomAlertSoundMeta[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refreshCustoms = useCallback(async () => {
    try {
      setCustoms(await listCustomAlertSounds());
    } catch {
      setError(t('settings.alertSounds.loadFail'));
    }
  }, [t]);

  useEffect(() => {
    void refreshCustoms();
  }, [refreshCustoms]);

  const onImport = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true);
    setError('');
    try {
      let lastId = '';
      for (const file of Array.from(files)) {
        if (!file.type.startsWith('audio/') && !/\.(mp3|wav|ogg|webm|m4a|aac|flac)$/i.test(file.name)) {
          setError(t('settings.alertSounds.badType', { name: file.name }));
          continue;
        }
        const meta = await addCustomAlertSound(file);
        lastId = `custom:${meta.id}`;
      }
      await refreshCustoms();
      if (lastId) {
        setAlertSoundId(lastId);
        playClick();
        void playAlertTone(lastId);
      }
    } catch {
      setError(t('settings.alertSounds.importFail'));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const onDeleteCustom = async (id: string) => {
    setBusy(true);
    setError('');
    try {
      await deleteCustomAlertSound(id);
      if (alertSoundId === `custom:${id}`) {
        setAlertSoundId(DEFAULT_ALERT_SOUND_ID);
      }
      await refreshCustoms();
    } catch {
      setError(t('settings.alertSounds.deleteFail'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border-t border-cv-border pt-4 mt-2 space-y-3" id="settings-alert-sounds">
      <div>
        <p className="text-sm font-medium">{t('settings.alertSounds.title')}</p>
        <p className="text-xs text-cv-muted mt-0.5">{t('settings.alertSounds.hint')}</p>
      </div>

      <label className="flex items-center gap-3 text-sm">
        <span className="text-cv-muted shrink-0 w-28">{t('settings.alertSounds.volume')}</span>
        <input
          type="range"
          min={0}
          max={100}
          value={Math.round(alertSoundVolume * 100)}
          onChange={(e) => setAlertSoundVolume(Number(e.target.value) / 100)}
          className="flex-1 accent-cv-accent"
        />
        <span className="text-xs tabular-nums w-10 text-right">{Math.round(alertSoundVolume * 100)}%</span>
      </label>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 max-h-72 overflow-y-auto pr-1">
        {ALERT_SOUND_CATALOG.map((s) => {
          const active = alertSoundId === s.id;
          const label = isEn ? s.labelEn : s.labelFr;
          return (
            <div
              key={s.id}
              className={`flex items-center gap-2 px-2.5 py-2 rounded border text-sm ${
                active ? 'border-cv-accent bg-cv-accent/10' : 'border-cv-border/50 bg-cv-surface/20'
              }`}
            >
              <button
                type="button"
                className="flex-1 text-left truncate"
                onClick={() => {
                  setAlertSoundId(s.id);
                  playClick();
                }}
                title={label}
              >
                {active && <Check className="w-3.5 h-3.5 inline mr-1 text-cv-accent" />}
                {label}
              </button>
              <button
                type="button"
                className="cv-btn-secondary !p-1.5"
                title={t('settings.alertSounds.preview')}
                onClick={() => {
                  void playAlertTone(s.id);
                }}
              >
                <Play className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
      </div>

      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium">{t('settings.alertSounds.customTitle')}</p>
          <button
            type="button"
            className="cv-btn-secondary text-xs inline-flex items-center gap-1"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
          >
            <Upload className="w-3.5 h-3.5" />
            {t('settings.alertSounds.addFile')}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="audio/*,.mp3,.wav,.ogg,.webm,.m4a,.aac,.flac"
            multiple
            className="hidden"
            onChange={(e) => void onImport(e.target.files)}
          />
        </div>
        <p className="text-xs text-cv-muted">{t('settings.alertSounds.customHint')}</p>
        {customs.length === 0 ? (
          <p className="text-xs text-cv-muted italic">{t('settings.alertSounds.customEmpty')}</p>
        ) : (
          <ul className="space-y-1.5">
            {customs.map((c) => {
              const sid = `custom:${c.id}`;
              const active = alertSoundId === sid;
              return (
                <li
                  key={c.id}
                  className={`flex items-center gap-2 px-2.5 py-2 rounded border text-sm ${
                    active ? 'border-cv-accent bg-cv-accent/10' : 'border-cv-border/50'
                  }`}
                >
                  <button
                    type="button"
                    className="flex-1 text-left truncate"
                    onClick={() => {
                      setAlertSoundId(sid);
                      playClick();
                    }}
                  >
                    {active && <Check className="w-3.5 h-3.5 inline mr-1 text-cv-accent" />}
                    {c.name}
                  </button>
                  <button
                    type="button"
                    className="cv-btn-secondary !p-1.5"
                    title={t('settings.alertSounds.preview')}
                    onClick={() => void playAlertTone(sid)}
                  >
                    <Play className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    className="cv-btn-secondary !p-1.5 text-cv-danger"
                    title={t('settings.alertSounds.delete')}
                    disabled={busy}
                    onClick={() => void onDeleteCustom(c.id)}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {error && <p className="text-xs text-cv-danger">{error}</p>}
    </div>
  );
}
