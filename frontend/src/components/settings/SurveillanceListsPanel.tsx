import { useCallback, useEffect, useState } from 'react';
import { Plus, Trash2, UserSearch } from 'lucide-react';
import { identityApi, type SurveillanceList } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import { useSound } from '@/hooks/useSound';

const PLATE_RE = /^[A-Z]{2}-\d{3}-[A-Z]{2}$/i;

type FaceEntry = {
  identifier?: string;
  label?: string;
  metadata?: {
    photo_url?: string;
    has_photo?: boolean;
    frigate_sync?: string;
    embedding?: unknown[];
  };
};

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
  const [busyList, setBusyList] = useState<string | null>(null);

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
    if (listType === 'plate_block' && newEntry.trim() && !PLATE_RE.test(newEntry.trim())) {
      setMessage('Format plaque attendu : AB-123-CD');
      return;
    }
    playClick();
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
      playSonar();
      setNewName('');
      setNewEntry('');
      setMessage(
        listType === 'face_watchlist'
          ? 'Liste créée — ajoutez des photos pour activer le matching.'
          : 'Liste créée.',
      );
      await load();
    } catch {
      setMessage('Échec création — vérifiez vos droits.');
    }
  };

  const addEntry = async (list: SurveillanceList) => {
    if (!orgId) return;
    const raw = (entryByList[list.id] ?? '').trim();
    if (!raw) return;
    playClick();
    setBusyList(list.id);
    try {
      if (list.list_type === 'face_watchlist') {
        const file = fileByList[list.id];
        if (!file) {
          setMessage('Photo requise pour enrôler un visage (pas de label seul).');
          return;
        }
        const { data } = await identityApi.enrollEntry(orgId, list.id, {
          label: raw,
          file,
        });
        const sync = data?.frigate_sync || '';
        setMessage(
          sync === 'ok'
            ? `Visage « ${raw} » enrôlé (InsightFace + Frigate).`
            : sync.startsWith('error')
              ? `Visage enrôlé (embedding OK) — sync Frigate: ${sync}`
              : `Visage « ${raw} » enrôlé (embedding OK).`,
        );
        setFileByList((m) => ({ ...m, [list.id]: null }));
      } else {
        if (!PLATE_RE.test(raw)) {
          setMessage('Format plaque attendu : AB-123-CD');
          return;
        }
        await identityApi.addEntry(orgId, list.id, {
          label: raw.toUpperCase(),
          plate_number: raw.toUpperCase(),
          identifier: raw.toUpperCase(),
        });
        setMessage('Entrée ajoutée.');
      }
      setEntryByList((m) => ({ ...m, [list.id]: '' }));
      playSonar();
      await load();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { error?: string } } })?.response?.data?.error ||
        'Ajout impossible.';
      setMessage(String(detail));
    } finally {
      setBusyList(null);
    }
  };

  const remove = async (id: string) => {
    if (!orgId) return;
    playClick();
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

  return (
    <div className="space-y-4">
      <p className="text-sm text-cv-muted">
        Listes requises pour les règles identité. Pour les visages : photo + nom — matching
        Frigate → InsightFace → Gemini (priorité dans cet ordre).
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
              placeholder="Plaque AB-123-CD"
            />
          </div>
        )}
      </div>
      <button type="button" onClick={() => void createList()} disabled={!newName.trim()} className="cv-btn-primary text-sm">
        <Plus className="w-4 h-4" />
        Créer la liste
      </button>

      {message && <p className="text-xs text-cv-accent">{message}</p>}

      {loading ? (
        <p className="text-sm text-cv-muted">Chargement…</p>
      ) : lists.length === 0 ? (
        <p className="text-sm text-cv-muted">Aucune liste — créez-en une pour débloquer les règles identité.</p>
      ) : (
        <div className="space-y-2 mt-4">
          {lists.map((list) => (
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

              {list.list_type === 'face_watchlist' && faceEntries(list).length > 0 && (
                <ul className="space-y-1.5">
                  {faceEntries(list).map((entry, idx) => {
                    const hasEmb = Array.isArray(entry.metadata?.embedding) && entry.metadata!.embedding!.length > 0;
                    return (
                      <li key={`${entry.identifier || idx}`} className="flex items-center gap-2 text-xs text-cv-muted">
                        {entry.metadata?.photo_url ? (
                          <img
                            src={entry.metadata.photo_url}
                            alt={entry.label || 'visage'}
                            className="w-8 h-8 rounded object-cover border border-cv-border"
                          />
                        ) : (
                          <span className="w-8 h-8 rounded border border-cv-border inline-flex items-center justify-center">
                            {hasEmb ? '✓' : '–'}
                          </span>
                        )}
                        <span className="truncate text-cv-text">{entry.label || entry.identifier || 'sans nom'}</span>
                        <span className="shrink-0">
                          {hasEmb ? 'embedding' : 'sans embedding'}
                          {entry.metadata?.frigate_sync ? ` · frigate:${entry.metadata.frigate_sync}` : ''}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}

              <div className="flex flex-col sm:flex-row gap-2">
                <input
                  className="cv-input text-sm flex-1"
                  value={entryByList[list.id] ?? ''}
                  onChange={(e) => setEntryByList((m) => ({ ...m, [list.id]: e.target.value }))}
                  placeholder={list.list_type === 'plate_block' ? 'AB-123-CD' : 'Nom du profil'}
                />
                {list.list_type === 'face_watchlist' && (
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="cv-input text-xs flex-1"
                    onChange={(e) =>
                      setFileByList((m) => ({
                        ...m,
                        [list.id]: e.target.files?.[0] ?? null,
                      }))
                    }
                  />
                )}
                <button
                  type="button"
                  onClick={() => void addEntry(list)}
                  disabled={busyList === list.id}
                  className="cv-btn-secondary text-xs shrink-0"
                >
                  {list.list_type === 'face_watchlist' ? 'Enrôler photo' : 'Ajouter'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
