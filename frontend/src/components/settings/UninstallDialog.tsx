import { useRef, useState } from 'react';
import {
  RefreshCcw, Eraser, Layers, Bomb, Trash2,
  CheckCircle2, XCircle, Loader2, ChevronRight, ChevronLeft,
  ShieldCheck, ShieldAlert, ShieldOff,
} from 'lucide-react';
import Modal from '@/components/ui/Modal';
import { systemApi, type UninstallMode, type SystemStreamEvent } from '@/api/client';

// ─── Mode definitions ────────────────────────────────────────────────────────

interface ModeCard {
  id: UninstallMode;
  icon: React.ElementType;
  label: string;
  badge: string;
  badgeColor: string;
  description: string;
  keeps: string[];
  removes: string[];
  duration: string;
  requireConfirm: boolean;
}

const MODES: ModeCard[] = [
  {
    id: 'restart',
    icon: RefreshCcw,
    label: 'Redémarrer les services',
    badge: 'SÛR',
    badgeColor: 'bg-emerald-500/15 text-emerald-400',
    description: 'Arrête puis redémarre tous les services CitéVision sans toucher aux données.',
    keeps: ['Données, volumes, configuration', 'Venv Python, node_modules', 'Vidéos et preuves'],
    removes: [],
    duration: '~30 secondes',
    requireConfirm: false,
  },
  {
    id: 'soft',
    icon: Eraser,
    label: 'Réinitialisation légère',
    badge: 'FAIBLE',
    badgeColor: 'bg-sky-500/15 text-sky-400',
    description: 'Arrête les services et supprime uniquement les fichiers temporaires et les sentinelles.',
    keeps: ['Volumes Docker (PostgreSQL, Redis, MinIO)', 'Venv Python, node_modules', 'Vidéos et preuves', 'Configuration runtime'],
    removes: ['Fichiers PID, logs temporaires', 'Sentinelles d\'installation'],
    duration: '~1 minute',
    requireConfirm: false,
  },
  {
    id: 'standard',
    icon: Layers,
    label: 'Désinstallation standard',
    badge: 'MODÉRÉ',
    badgeColor: 'bg-amber-500/15 text-amber-400',
    description: 'Arrête et supprime les bases de données, sans retélécharger Python ni les dépendances Node.',
    keeps: ['Venv Python, node_modules', 'Images Docker', 'Vidéos et preuves'],
    removes: ['Volumes Docker (PostgreSQL, Redis, MinIO)', 'Logs, configuration runtime', 'Sentinelles'],
    duration: '~2 minutes (réinstall rapide)',
    requireConfirm: false,
  },
  {
    id: 'full',
    icon: Trash2,
    label: 'Désinstallation complète',
    badge: 'ÉLEVÉ',
    badgeColor: 'bg-orange-500/15 text-orange-400',
    description: 'Suppression totale des dépendances et volumes. Conserve seulement vos vidéos et preuves.',
    keeps: ['Vidéos et preuves (data/)'],
    removes: ['Volumes Docker', 'Venv Python (~/.citevision-v2)', 'node_modules', 'Logs, generated.env', 'Service système'],
    duration: '~15 minutes (nouvelle installation complète)',
    requireConfirm: true,
  },
  {
    id: 'nuclear',
    icon: Bomb,
    label: 'Suppression totale',
    badge: 'CRITIQUE',
    badgeColor: 'bg-red-500/15 text-red-400',
    description: 'Suppression absolue de CitéVision et de toutes ses données. Irréversible.',
    keeps: [],
    removes: ['Volumes Docker', 'Venv Python, node_modules', 'Vidéos, preuves, evidence', 'Service système', 'Logs, configuration, .env'],
    duration: '~15–20 minutes (réinstallation from scratch)',
    requireConfirm: true,
  },
];

function riskIcon(mode: UninstallMode) {
  if (mode === 'restart' || mode === 'soft') return <ShieldCheck className="w-4 h-4" />;
  if (mode === 'standard') return <ShieldAlert className="w-4 h-4" />;
  return <ShieldOff className="w-4 h-4" />;
}

// ─── Step components ─────────────────────────────────────────────────────────

function StepIndicator({ step }: { step: 1 | 2 | 3 }) {
  return (
    <div className="flex items-center gap-2 mb-6">
      {[1, 2, 3].map((n) => (
        <div key={n} className="flex items-center gap-2">
          <div
            className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold border transition-colors ${
              n === step
                ? 'bg-cv-accent text-cv-deep border-cv-accent'
                : n < step
                  ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40'
                  : 'bg-cv-surface text-cv-muted border-cv-border'
            }`}
          >
            {n < step ? <CheckCircle2 className="w-4 h-4" /> : n}
          </div>
          {n < 3 && (
            <div className={`h-px w-6 transition-colors ${n < step ? 'bg-emerald-500/40' : 'bg-cv-border'}`} />
          )}
        </div>
      ))}
      <span className="ml-2 text-xs text-cv-muted">
        {step === 1 ? 'Sélection' : step === 2 ? 'Confirmation' : 'Progression'}
      </span>
    </div>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function UninstallDialog({ open, onClose }: Props) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [selectedMode, setSelectedMode] = useState<UninstallMode>('soft');
  const [confirmInput, setConfirmInput] = useState('');
  const [logs, setLogs] = useState<SystemStreamEvent[]>([]);
  const [done, setDone] = useState(false);
  const [ok, setOk] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [reloadCountdown, setReloadCountdown] = useState(0);
  const logRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const reloadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const card = MODES.find((m) => m.id === selectedMode)!;
  const Icon = card.icon;

  function handleClose() {
    if (step === 3 && !done) return; // prevent closing while running
    abortRef.current?.abort();
    if (reloadTimerRef.current) clearTimeout(reloadTimerRef.current);
    // reset state for next open
    setStep(1);
    setSelectedMode('soft');
    setConfirmInput('');
    setLogs([]);
    setDone(false);
    setOk(false);
    setReloading(false);
    setReloadCountdown(0);
    onClose();
  }

  function scheduleReload(seconds: number) {
    setReloading(true);
    setReloadCountdown(seconds);
    let remaining = seconds;
    const tick = () => {
      remaining--;
      setReloadCountdown(remaining);
      if (remaining <= 0) {
        window.location.reload();
      } else {
        reloadTimerRef.current = setTimeout(tick, 1000);
      }
    };
    reloadTimerRef.current = setTimeout(tick, 1000);
  }

  async function startUninstall() {
    setStep(3);
    setLogs([]);
    setDone(false);
    setOk(false);
    setReloading(false);
    abortRef.current = new AbortController();
    // Modes that stop the backend — connection drop is expected and treated as success
    const stopsServices = true; // all modes eventually call stop-linux.sh
    try {
      for await (const evt of systemApi.streamUninstall(selectedMode, abortRef.current.signal)) {
        setLogs((prev) => [...prev, evt]);
        if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
        if (evt.event === 'done') {
          setDone(true);
          setOk(true);
          // For restart mode: auto-reload after 35s to reconnect
          if (selectedMode === 'restart') scheduleReload(35);
          break;
        }
        if (evt.event === 'error' && evt.ok === false) { setDone(true); setOk(false); break; }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      // Connection lost = services are stopping = expected for all uninstall modes
      if (stopsServices && (msg.includes('fetch') || msg.includes('network') || msg.includes('aborted'))) {
        setLogs((prev) => [
          ...prev,
          { event: 'step', message: 'Connection perdue — les services s\'arretent. C\'est normal.' },
        ]);
        setDone(true);
        setOk(true);
        if (selectedMode === 'restart') {
          setLogs((prev) => [...prev, { event: 'info', message: 'Rechargement automatique dans 35 secondes...' }]);
          scheduleReload(35);
        }
      } else {
        setLogs((prev) => [...prev, { event: 'error', message: msg }]);
        setDone(true);
        setOk(false);
      }
    }
  }

  const canConfirm =
    !card.requireConfirm || confirmInput === 'CONFIRMER';

  return (
    <Modal
      open={open}
      onClose={handleClose}
      maxWidth="2xl"
      title={
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-red-500/10">
            <Trash2 className="w-5 h-5 text-red-400" />
          </div>
          <span>Gestion de l&apos;installation</span>
        </div>
      }
      footer={
        step === 1 ? (
          <>
            <button type="button" className="cv-btn-secondary" onClick={handleClose}>
              Annuler
            </button>
            <button
              type="button"
              className="cv-btn-primary flex items-center gap-2"
              onClick={() => setStep(2)}
            >
              Continuer <ChevronRight className="w-4 h-4" />
            </button>
          </>
        ) : step === 2 ? (
          <>
            <button
              type="button"
              className="cv-btn-secondary flex items-center gap-2"
              onClick={() => { setConfirmInput(''); setStep(1); }}
            >
              <ChevronLeft className="w-4 h-4" /> Retour
            </button>
            <button
              type="button"
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                canConfirm
                  ? 'bg-red-500 hover:bg-red-600 text-white'
                  : 'bg-cv-surface text-cv-muted cursor-not-allowed opacity-60'
              }`}
              disabled={!canConfirm}
              onClick={() => void startUninstall()}
            >
              {riskIcon(selectedMode)}
              {card.label}
            </button>
          </>
        ) : done ? (
          <button type="button" className="cv-btn-primary" onClick={handleClose}>
            Fermer
          </button>
        ) : undefined
      }
    >
      <StepIndicator step={step} />

      {/* ── Step 1: Mode selection ── */}
      {step === 1 && (
        <div className="space-y-2.5">
          {MODES.map((m) => {
            const MIcon = m.icon;
            const isSelected = selectedMode === m.id;
            return (
              <button
                key={m.id}
                type="button"
                onClick={() => setSelectedMode(m.id)}
                className={`w-full text-left rounded-xl border p-4 transition-all ${
                  isSelected
                    ? 'border-cv-accent bg-cv-accent/5 ring-1 ring-cv-accent/30'
                    : 'border-cv-border bg-cv-surface/50 hover:border-cv-border/80 hover:bg-cv-surface'
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className={`mt-0.5 p-2 rounded-lg shrink-0 ${isSelected ? 'bg-cv-accent/10' : 'bg-cv-surface'}`}>
                    <MIcon className={`w-4 h-4 ${isSelected ? 'text-cv-accent' : 'text-cv-muted'}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className={`text-sm font-semibold ${isSelected ? 'text-cv-text' : 'text-cv-text/80'}`}>
                        {m.label}
                      </span>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wide ${m.badgeColor}`}>
                        {m.badge}
                      </span>
                    </div>
                    <p className="text-xs text-cv-muted leading-relaxed">{m.description}</p>
                    {isSelected && (
                      <div className="mt-2.5 grid grid-cols-2 gap-2">
                        {m.keeps.length > 0 && (
                          <div>
                            <p className="text-[10px] font-semibold text-emerald-400 uppercase tracking-wider mb-1">
                              Conserve
                            </p>
                            {m.keeps.map((k) => (
                              <p key={k} className="text-[11px] text-emerald-400/80 flex items-start gap-1">
                                <CheckCircle2 className="w-3 h-3 shrink-0 mt-0.5" />{k}
                              </p>
                            ))}
                          </div>
                        )}
                        {m.removes.length > 0 && (
                          <div>
                            <p className="text-[10px] font-semibold text-red-400 uppercase tracking-wider mb-1">
                              Supprime
                            </p>
                            {m.removes.map((r) => (
                              <p key={r} className="text-[11px] text-red-400/80 flex items-start gap-1">
                                <XCircle className="w-3 h-3 shrink-0 mt-0.5" />{r}
                              </p>
                            ))}
                          </div>
                        )}
                        {m.removes.length === 0 && m.keeps.length > 0 && (
                          <div>
                            <p className="text-[10px] font-semibold text-emerald-400 uppercase tracking-wider mb-1">
                              Supprime
                            </p>
                            <p className="text-[11px] text-cv-muted italic">Rien — opération non destructive</p>
                          </div>
                        )}
                      </div>
                    )}
                    {isSelected && (
                      <p className="mt-2 text-[11px] text-cv-muted">⏱ {m.duration}</p>
                    )}
                  </div>
                  <div className={`w-4 h-4 rounded-full border-2 shrink-0 mt-1 transition-colors ${
                    isSelected ? 'border-cv-accent bg-cv-accent' : 'border-cv-border'
                  }`} />
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* ── Step 2: Summary + confirmation ── */}
      {step === 2 && (
        <div className="space-y-4">
          {/* Summary card */}
          <div className={`rounded-xl border p-4 ${
            selectedMode === 'nuclear' ? 'border-red-500/40 bg-red-500/5'
            : selectedMode === 'full' ? 'border-orange-500/40 bg-orange-500/5'
            : 'border-cv-border bg-cv-surface/50'
          }`}>
            <div className="flex items-center gap-3 mb-3">
              <div className="p-2 rounded-lg bg-cv-surface">
                <Icon className="w-5 h-5 text-cv-accent" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-cv-text">{card.label}</span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${card.badgeColor}`}>
                    {card.badge}
                  </span>
                </div>
                <p className="text-xs text-cv-muted mt-0.5">{card.description}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 mt-3">
              {card.keeps.length > 0 && (
                <div className="rounded-lg bg-emerald-500/5 border border-emerald-500/20 p-3">
                  <p className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider mb-2">
                    Vous conservez
                  </p>
                  {card.keeps.map((k) => (
                    <p key={k} className="text-xs text-emerald-300/80 flex items-start gap-1.5 mb-0.5">
                      <CheckCircle2 className="w-3.5 h-3.5 shrink-0 mt-0.5" />{k}
                    </p>
                  ))}
                </div>
              )}
              {card.removes.length > 0 && (
                <div className="rounded-lg bg-red-500/5 border border-red-500/20 p-3">
                  <p className="text-[10px] font-bold text-red-400 uppercase tracking-wider mb-2">
                    Vous perdez
                  </p>
                  {card.removes.map((r) => (
                    <p key={r} className="text-xs text-red-300/80 flex items-start gap-1.5 mb-0.5">
                      <XCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />{r}
                    </p>
                  ))}
                </div>
              )}
              {card.removes.length === 0 && (
                <div className="col-span-2 rounded-lg bg-emerald-500/5 border border-emerald-500/20 p-3 text-center">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 mx-auto mb-1" />
                  <p className="text-xs text-emerald-400">Opération non destructive — aucune donnée supprimée</p>
                </div>
              )}
            </div>

            <p className="mt-3 text-[11px] text-cv-muted">⏱ Durée estimée : {card.duration}</p>
          </div>

          {/* Confirmation input for destructive modes */}
          {card.requireConfirm && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4">
              <div className="flex items-start gap-2 mb-3">
                <ShieldOff className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                <p className="text-sm text-red-300">
                  Cette opération est <strong>irréversible</strong>. Tapez{' '}
                  <code className="bg-red-900/30 px-1 rounded font-mono text-red-200">CONFIRMER</code>{' '}
                  pour continuer.
                </p>
              </div>
              <input
                type="text"
                value={confirmInput}
                onChange={(e) => setConfirmInput(e.target.value)}
                placeholder="CONFIRMER"
                className="cv-input w-full font-mono text-center tracking-widest"
                autoComplete="off"
                autoFocus
              />
            </div>
          )}
        </div>
      )}

      {/* ── Step 3: Progress ── */}
      {step === 3 && (
        <div className="space-y-4">
          {!done && (
            <div className="flex items-center gap-2.5 text-sm text-cv-muted p-3 rounded-lg bg-cv-surface/50 border border-cv-border/50">
              <Loader2 className="w-4 h-4 animate-spin text-cv-accent shrink-0" />
              <span>{card.label} en cours — ne fermez pas cette fenêtre…</span>
            </div>
          )}
          {done && (
            <div
              className={`flex items-center gap-3 p-3 rounded-lg text-sm ${
                ok
                  ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400'
                  : 'bg-red-500/10 border border-red-500/30 text-red-400'
              }`}
            >
              {ok ? <CheckCircle2 className="w-5 h-5 shrink-0" /> : <XCircle className="w-5 h-5 shrink-0" />}
              <div>
                <p className="font-semibold">
                  {ok ? 'Opération terminée avec succès' : 'L\'opération a rencontré des erreurs'}
                </p>
                {ok && reloading && (
                  <p className="text-xs mt-0.5 opacity-80 font-mono">
                    Rechargement dans {reloadCountdown}s...
                  </p>
                )}
                {ok && !reloading && selectedMode === 'restart' && (
                  <button
                    type="button"
                    className="text-xs mt-1 underline opacity-80 hover:opacity-100"
                    onClick={() => window.location.reload()}
                  >
                    Recharger la page maintenant
                  </button>
                )}
                {ok && selectedMode !== 'restart' && (
                  <p className="text-xs mt-0.5 opacity-80">
                    Pour réinstaller : setup.bat (Windows) ou bash scripts/setup-wsl.sh (Linux).
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Progress bar */}
          {!done && (
            <div className="h-1 w-full bg-cv-border rounded-full overflow-hidden">
              <div className="h-full bg-cv-accent rounded-full animate-pulse w-1/2" />
            </div>
          )}

          {/* Log terminal */}
          <div
            ref={logRef}
            className="h-52 overflow-y-auto rounded-xl bg-cv-deep/90 p-3 font-mono text-xs space-y-0.5 border border-cv-border/50"
          >
            {logs.length === 0 && (
              <span className="text-cv-muted">En attente du premier événement…</span>
            )}
            {logs.map((line, i) => (
              <div
                key={i}
                className={
                  line.event === 'error'
                    ? 'text-red-400'
                    : line.event === 'warn'
                      ? 'text-amber-400'
                      : line.event === 'ok' || line.event === 'done'
                        ? 'text-emerald-400'
                        : line.event === 'step'
                          ? 'text-cv-accent font-semibold'
                          : 'text-cv-muted'
                }
              >
                {line.event === 'step' ? '▶ ' : '  '}{line.message}
              </div>
            ))}
          </div>
        </div>
      )}
    </Modal>
  );
}
