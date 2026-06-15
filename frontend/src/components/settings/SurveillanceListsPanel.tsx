import { useCallback, useEffect, useState } from 'react';
import { Plus, Trash2, UserSearch } from 'lucide-react';
import { identityApi, type SurveillanceList } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import { useSound } from '@/hooks/useSound';

const PLATE_RE = /^[A-Z]{2}-\d{3}-[A-Z]{2}$/i;

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
    const entries = newEntry.trim()
      ? [{ label: newEntry.trim(), plate_number: newEntry.trim().toUpperCase() }]
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
      setMessage('Liste créée.');
      await load();
    } catch {
      setMessage('Échec création — vérifiez vos droits.');
    }
  };

  const addEntry = async (list: SurveillanceList) => {
    if (!orgId) return;
    const raw = (entryByList[list.id] ?? '').trim();
    if (!raw) return;
    if (list.list_type === 'plate_block' && !PLATE_RE.test(raw)) {
      setMessage('Format plaque attendu : AB-123-CD');
      return;
    }
    playClick();
    try {
      await identityApi.addEntry(orgId, list.id, {
        label: raw,
        plate_number: list.list_type === 'plate_block' ? raw.toUpperCase() : undefined,
      });
      setEntryByList((m) => ({ ...m, [list.id]: '' }));
      setMessage('Entrée ajoutée.');
      await load();
    } catch {
      setMessage('Ajout impossible.');
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

  return (
    <div className="space-y-4">
      <p className="text-sm text-cv-muted">
        Listes requises pour activer les règles identité (visage liste de surveillance, plaques bloquées, etc.).
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
        <div className="sm:col-span-2">
          <label className="cv-label">Première entrée (optionnel)</label>
          <input
            className="cv-input"
            value={newEntry}
            onChange={(e) => setNewEntry(e.target.value)}
            placeholder={listType === 'face_watchlist' ? 'Nom ou ID profil' : 'Plaque AB-123-CD'}
          />
        </div>
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
              <div className="flex gap-2">
                <input
                  className="cv-input text-sm flex-1"
                  value={entryByList[list.id] ?? ''}
                  onChange={(e) => setEntryByList((m) => ({ ...m, [list.id]: e.target.value }))}
                  placeholder={list.list_type === 'plate_block' ? 'AB-123-CD' : 'Nouvelle entrée'}
                />
                <button type="button" onClick={() => void addEntry(list)} className="cv-btn-secondary text-xs shrink-0">
                  Ajouter
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
