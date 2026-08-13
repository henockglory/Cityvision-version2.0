import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Plus, Trash2, UserSearch, ImageOff } from 'lucide-react';
import { identityApi, type SurveillanceList } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import { useSound } from '@/hooks/useSound';
import { buildEvidenceAssetUrl, normalizeEvidenceApiUrl } from '@/lib/evidence';
import { EvidenceThumbnail } from '@/components/evidence/EvidenceMedia';

type FaceEntry = {
  identifier?: string;
  label?: string;
  metadata?: {
    photo_url?: string;
    photo_object_key?: string;
    has_photo?: boolean;
    frigate_sync?: string;
    embedding?: unknown[];
    entry_id?: string;
  };
};

type RowStatus = { tone: 'info' | 'ok' | 'err'; text: string };

function humanizeEnrollError(raw: string, status?: number): string {
  const s = (raw || '').toLowerCase();
  if (status === 404 || s.includes('404')) {
    return 'Route enrôlement absente — backend à reconstruire / redémarrer.';
  }
  if (s.includes('no_face')) {
    return 'Aucun visage détecté dans la photo (visage net, de face, bien éclairé).';
  }
  if (s.includes('decode_failed') || s.includes('empty file')) {
    return 'Image illisible — utilisez JPEG/PNG/WebP.';
  }
  if (s.includes('insightface_not_loaded') || s.includes('ai engine unavailable')) {
    return 'Moteur visage indisponible — attendre le démarrage AI puis réessayer.';
  }
  if (s.includes('multipart') || s.includes('file required')) {
    return 'Envoi photo échoué (multipart) — recharger la page puis réessayer.';
  }
  if (s.includes('label required')) {
    return 'Nom du profil requis.';
  }
  if (s.includes('network') || s.includes('timeout') || s.includes('exceeded')) {
    return 'Délai dépassé / réseau — réessayez (InsightFace peut prendre quelques secondes).';
  }
  return raw || 'Ajout impossible.';
}

/** Resolve authenticated API path for a watchlist enrollment photo. */
function watchlistPhotoApiUrl(entry: FaceEntry, orgId: string | null | undefined): string | undefined {
  if (!orgId) return undefined;
  const key = String(entry.metadata?.photo_object_key || '').trim();
  if (key) return buildEvidenceAssetUrl(orgId, key);
  const raw = String(entry.metadata?.photo_url || '').trim();
  if (!raw) return undefined;
  return normalizeEvidenceApiUrl(raw);
}

function LocalFilePreview({ file, label }: { file: File; label?: string }) {
  const url = useMemo(() => URL.createObjectURL(file), [file]);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);
  return (
    <div className="relative w-16 h-16 rounded-lg overflow-hidden border border-cv-accent/50 bg-cv-deep/40 shrink-0">
      <img src={url} alt={label || file.name} className="w-full h-full object-cover" />
      <span className="absolute bottom-0 inset-x-0 text-[9px] leading-tight px-0.5 py-0.5 bg-black/65 text-white truncate">
        à enrôler
      </span>
    </div>
  );
}

function WatchlistFaceThumb({
  apiUrl,
  label,
}: {
  apiUrl: string | undefined;
  label: string;
}) {
  if (!apiUrl) {
    return (
      <div className="w-16 h-16 rounded-lg border border-cv-border bg-cv-deep/40 flex flex-col items-center justify-center gap-0.5 text-cv-muted">
        <ImageOff className="w-4 h-4" />
        <span className="text-[9px]">sans photo</span>
      </div>
    );
  }
  return (
    <div className="w-16 h-16 rounded-lg overflow-hidden border border-cv-border bg-cv-deep/40 shrink-0">
      <EvidenceThumbnail apiUrl={apiUrl} className="w-full h-full object-cover" />
      <span className="sr-only">{label}</span>
    </div>
  );
}

export default function SurveillanceListsPanel() {
  const orgId = useAuthStore((s) => s.orgId);
  const { playClick, playSonar } = useSound();
  const [lists, setLists] = useState<SurveillanceList[]>([]);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState('');
  const [newEntry, setNewEntry] = useState('');
  const [listType, setListType] = useState<'face_watchlist' | 'plate_block'>('face_watchlist');
  const [message, setMessage] = useState('');
  const [entryByList, setEntryByList] = useState<Record<string, string>>({});
  const [fileByList, setFileByList] = useState<Record<string, File | null>>({});
  const [fileKeyByList, setFileKeyByList] = useState<Record<string, number>>({});
  const [busyList, setBusyList] = useState<string | null>(null);
  const [statusByList, setStatusByList] = useState<Record<string, RowStatus | undefined>>({});
  const enrollLock = useRef<Set<string>>(new Set());

  const setRowStatus = (listId: string, status: RowStatus | undefined) => {
    setStatusByList((m) => ({ ...m, [listId]: status }));
    if (status) setMessage(status.text);
  };

  const load = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try {
      const { data } = await identityApi.list(orgId);
      setLists(Array.isArray(data) ? data : []);
    } catch {
      setLists([]);
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    void load();
  }, [load]);

  const createList = async () => {
    if (!orgId || !newName.trim()) return;
    try {
      playClick();
    } catch {
      /* ignore audio */
    }
    const entries =
      listType === 'plate_block' && newEntry.trim()
        ? [{
            label: newEntry.trim().toUpperCase(),
            plate_number: newEntry.trim().toUpperCase(),
            identifier: newEntry.trim().toUpperCase(),
          }]
        : [];
    try {
      await identityApi.create(orgId, {
        name: newName.trim(),
        list_type: listType,
        entries,
      });
      try {
        playSonar();
      } catch {
        /* ignore */
      }
      setNewName('');
      setNewEntry('');
      setMessage(
        listType === 'face_watchlist'
          ? 'Liste créée — choisissez une photo pour enrôler automatiquement.'
          : 'Liste créée.',
      );
      await load();
    } catch {
      setMessage('Échec création — vérifiez vos droits.');
    }
  };

  const enrollFace = async (list: SurveillanceList, file: File, labelHint?: string) => {
    if (!orgId) {
      setRowStatus(list.id, { tone: 'err', text: 'Organisation non résolue — reconnectez-vous.' });
      return;
    }
    if (enrollLock.current.has(list.id) || busyList === list.id) return;
    enrollLock.current.add(list.id);

    let label = (labelHint ?? entryByList[list.id] ?? '').trim();
    if (!label) {
      label = file.name.replace(/\.[^.]+$/, '').trim() || 'Profil';
      setEntryByList((m) => ({ ...m, [list.id]: label }));
    }

    setBusyList(list.id);
    setFileByList((m) => ({ ...m, [list.id]: file }));
    setRowStatus(list.id, {
      tone: 'info',
      text: `Envoi de « ${label} » — détection visage + embedding…`,
    });

    try {
      try {
        playClick();
      } catch {
        /* ignore */
      }
      const { data } = await identityApi.enrollEntry(orgId, list.id, { label, file });
      const sync = data?.frigate_sync || '';
      const okText =
        sync === 'ok'
          ? `Visage « ${label} » enrôlé (InsightFace + Frigate).`
          : sync.startsWith('error')
            ? `Visage « ${label} » enrôlé (embedding OK) — Frigate: ${sync}`
            : `Visage « ${label} » enrôlé (embedding OK).`;
      setRowStatus(list.id, { tone: 'ok', text: okText });
      setEntryByList((m) => ({ ...m, [list.id]: '' }));
      setFileByList((m) => ({ ...m, [list.id]: null }));
      setFileKeyByList((m) => ({ ...m, [list.id]: (m[list.id] || 0) + 1 }));
      try {
        playSonar();
      } catch {
        /* ignore */
      }
      await load();
    } catch (err: unknown) {
      const data = (err as { response?: { data?: { error?: string; detail?: string } } })?.response
        ?.data;
      const status = (err as { response?: { status?: number } })?.response?.status;
      const rawMsg =
        data?.error ||
        (typeof data?.detail === 'string' ? data.detail : '') ||
        (err as { message?: string })?.message ||
        '';
      setRowStatus(list.id, {
        tone: 'err',
        text: humanizeEnrollError(String(rawMsg), status),
      });
    } finally {
      enrollLock.current.delete(list.id);
      setBusyList(null);
    }
  };

  const addEntry = async (list: SurveillanceList) => {
    if (list.list_type === 'face_watchlist') {
      const file = fileByList[list.id];
      if (!file) {
        setRowStatus(list.id, {
          tone: 'err',
          text: 'Choisissez d’abord une photo (JPEG/PNG) — l’envoi démarre aussitôt.',
        });
        return;
      }
      await enrollFace(list, file);
      return;
    }

    if (!orgId) {
      setMessage('Organisation non résolue — reconnectez-vous.');
      return;
    }
    const raw = (entryByList[list.id] ?? '').trim();
    if (!raw) {
      setRowStatus(list.id, { tone: 'err', text: 'Indiquez une plaque ou identifiant.' });
      return;
    }
    setBusyList(list.id);
    setRowStatus(list.id, { tone: 'info', text: 'Ajout de la plaque…' });
    try {
      await identityApi.addEntry(orgId, list.id, {
        label: raw.toUpperCase(),
        plate_number: raw.toUpperCase(),
        identifier: raw.toUpperCase(),
      });
      setRowStatus(list.id, { tone: 'ok', text: 'Entrée ajoutée.' });
      setEntryByList((m) => ({ ...m, [list.id]: '' }));
      await load();
    } catch {
      setRowStatus(list.id, { tone: 'err', text: 'Ajout impossible.' });
    } finally {
      setBusyList(null);
    }
  };

  const remove = async (id: string) => {
    if (!orgId) return;
    try {
      playClick();
    } catch {
      /* ignore */
    }
    try {
      await identityApi.delete(orgId, id);
      await load();
    } catch {
      setMessage('Suppression impossible.');
    }
  };

  const typeLabel = (t: string) => {
    if (t === 'face_watchlist') return 'Visages surveillance';
    if (t === 'plate_block') return 'Plaques bloquées';
    if (t === 'plate_allow') return 'Plaques autorisées';
    return t;
  };

  const faceEntries = (list: SurveillanceList): FaceEntry[] => {
    if (!Array.isArray(list.entries)) return [];
    return list.entries as FaceEntry[];
  };

  const toneClass = (tone: RowStatus['tone']) => {
    if (tone === 'ok') return 'text-emerald-600 bg-emerald-50 border-emerald-200';
    if (tone === 'err') return 'text-red-600 bg-red-50 border-red-200';
    return 'text-cv-accent bg-cv-surface border-cv-border';
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-cv-muted">
        Listes requises pour les règles identité. Pour les visages : photo + nom, puis cliquez
        « Enrôler photo » (Frigate → InsightFace → Gemini). Les miniatures affichent le contenu réel de la liste.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="cv-label">Type de liste</label>
          <select className="cv-input" value={listType} onChange={(e) => setListType(e.target.value as typeof listType)}>
            <option value="face_watchlist">Liste visages surveillance</option>
            <option value="plate_block">Plaques bloquées</option>
          </select>
        </div>
        <div>
          <label className="cv-label">Nom de la liste</label>
          <input className="cv-input" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Ex: Personnel autorisé" />
        </div>
        {listType === 'plate_block' && (
          <div className="sm:col-span-2">
            <label className="cv-label">Première plaque (optionnel)</label>
            <input
              className="cv-input"
              value={newEntry}
              onChange={(e) => setNewEntry(e.target.value)}
              placeholder="Plaque ou identifiant"
            />
          </div>
        )}
      </div>
      <button type="button" onClick={() => void createList()} disabled={!newName.trim()} className="cv-btn-primary text-sm">
        <Plus className="w-4 h-4" />
        Créer la liste
      </button>

      {message && (
        <p className="text-sm font-medium px-3 py-2 rounded-lg border border-cv-border bg-cv-surface text-cv-text">
          {message}
        </p>
      )}

      {loading ? (
        <p className="text-sm text-cv-muted flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> Chargement…
        </p>
      ) : lists.length === 0 ? (
        <p className="text-sm text-cv-muted">Aucune liste — créez-en une pour débloquer les règles identité.</p>
      ) : (
        <div className="space-y-2 mt-4">
          {lists.map((list) => {
            const busy = busyList === list.id;
            const row = statusByList[list.id];
            const pendingFile = fileByList[list.id];
            const faces = faceEntries(list);
            return (
              <div key={list.id} className="p-3 rounded-lg border border-cv-border space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <UserSearch className="w-4 h-4 text-cv-accent shrink-0" />
                    <div className="min-w-0">
                      <p className="font-medium text-sm truncate">{list.name}</p>
                      <p className="text-xs text-cv-muted">
                        {typeLabel(list.list_type)} · {Array.isArray(list.entries) ? list.entries.length : 0} entrée(s)
                      </p>
                    </div>
                  </div>
                  <button type="button" onClick={() => void remove(list.id)} className="cv-btn-ghost p-1.5 text-red-400 shrink-0">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>

                {list.list_type === 'face_watchlist' && (faces.length > 0 || pendingFile) && (
                  <div className="space-y-1.5">
                    <p className="text-[11px] text-cv-muted">Aperçu des identités</p>
                    <ul className="flex flex-wrap gap-3">
                      {faces.map((entry, idx) => {
                        const hasEmb = Array.isArray(entry.metadata?.embedding) && entry.metadata!.embedding!.length > 0;
                        const label = entry.label || entry.identifier || 'sans nom';
                        const apiUrl = watchlistPhotoApiUrl(entry, orgId);
                        return (
                          <li
                            key={`${entry.identifier || entry.metadata?.entry_id || idx}`}
                            className="flex flex-col items-center gap-1 w-[4.5rem]"
                            title={`${label}${hasEmb ? ' · embedding OK' : ''}${entry.metadata?.frigate_sync ? ` · frigate:${entry.metadata.frigate_sync}` : ''}`}
                          >
                            <WatchlistFaceThumb apiUrl={apiUrl} label={label} />
                            <span className="text-[10px] text-cv-text truncate w-full text-center">{label}</span>
                            <span className="text-[9px] text-cv-muted truncate w-full text-center">
                              {hasEmb ? 'OK' : 'sans emb.'}
                              {entry.metadata?.frigate_sync === 'ok' ? ' · Frigate' : ''}
                            </span>
                          </li>
                        );
                      })}
                      {pendingFile && (
                        <li className="flex flex-col items-center gap-1 w-[4.5rem]">
                          <LocalFilePreview file={pendingFile} label={entryByList[list.id]} />
                          <span className="text-[10px] text-cv-accent truncate w-full text-center">
                            {entryByList[list.id]?.trim() || pendingFile.name.replace(/\.[^.]+$/, '')}
                          </span>
                        </li>
                      )}
                    </ul>
                  </div>
                )}

                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    className="cv-input text-sm flex-1"
                    value={entryByList[list.id] ?? ''}
                    onChange={(e) => setEntryByList((m) => ({ ...m, [list.id]: e.target.value }))}
                    placeholder={list.list_type === 'plate_block' ? 'Plaque ou identifiant' : 'Nom du profil (sinon = nom fichier)'}
                    disabled={busy}
                  />
                  {list.list_type === 'face_watchlist' && (
                    <input
                      key={`file-${list.id}-${fileKeyByList[list.id] || 0}`}
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      className="cv-input text-xs flex-1"
                      disabled={busy}
                      onChange={(e) => {
                        const file = e.target.files?.[0] ?? null;
                        setFileByList((m) => ({ ...m, [list.id]: file }));
                        if (file) {
                          setRowStatus(list.id, {
                            tone: 'info',
                            text: `Photo prête : ${file.name} — cliquez « Enrôler photo ».`,
                          });
                        } else {
                          setRowStatus(list.id, undefined);
                        }
                      }}
                    />
                  )}
                  <button
                    type="button"
                    onClick={() => void addEntry(list)}
                    disabled={busy || (list.list_type === 'face_watchlist' && !fileByList[list.id])}
                    className="cv-btn-secondary text-xs shrink-0 inline-flex items-center gap-1.5 min-w-[8.5rem] justify-center"
                  >
                    {busy ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        Envoi…
                      </>
                    ) : list.list_type === 'face_watchlist' ? (
                      'Enrôler photo'
                    ) : (
                      'Ajouter'
                    )}
                  </button>
                </div>

                {row && (
                  <p className={`text-xs px-2.5 py-1.5 rounded border ${toneClass(row.tone)} flex items-center gap-1.5`}>
                    {busy && row.tone === 'info' ? <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" /> : null}
                    <span>{row.text}</span>
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
