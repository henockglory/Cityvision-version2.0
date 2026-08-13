import { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, Star, Trash2 } from 'lucide-react';
import {
  platePatternsApi,
  type PlatePattern,
  type PlateSegment,
} from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import { useSound } from '@/hooks/useSound';
import PremiumSelect from '@/components/ui/PremiumSelect';

const CHARSETS: { value: PlateSegment['charset']; label: string }[] = [
  { value: 'A-Z', label: 'Lettres (A–Z)' },
  { value: '0-9', label: 'Chiffres (0–9)' },
  { value: 'A-Z0-9', label: 'Alphanumérique' },
];

function emptySegment(): PlateSegment {
  return { charset: 'A-Z', count: 2 };
}

function previewRegex(segments: PlateSegment[]): string {
  if (!segments.length) return '^[A-Z0-9]{4,12}$';
  const parts = segments.map((s) => {
    const cls =
      s.charset === '0-9' ? '[0-9]' : s.charset === 'A-Z0-9' ? '[A-Z0-9]' : '[A-Z]';
    return `${cls}{${Math.max(1, Math.min(12, s.count || 1))}}`;
  });
  return `^${parts.join('')}$`;
}

export default function PlatePatternsPanel() {
  const orgId = useAuthStore((s) => s.orgId);
  const { playClick } = useSound();
  const [patterns, setPatterns] = useState<PlatePattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [name, setName] = useState('');
  const [segments, setSegments] = useState<PlateSegment[]>([
    emptySegment(),
    { charset: '0-9', count: 4 },
    emptySegment(),
  ]);
  const [busy, setBusy] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try {
      const { data } = await platePatternsApi.list(orgId);
      setPatterns(Array.isArray(data) ? data : []);
    } catch {
      setPatterns([]);
      setMessage('Impossible de charger les compositions de plaque.');
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    void load();
  }, [load]);

  const preview = useMemo(() => previewRegex(segments), [segments]);

  const resetForm = () => {
    setEditId(null);
    setName('');
    setSegments([emptySegment(), { charset: '0-9', count: 4 }, emptySegment()]);
  };

  const startEdit = (p: PlatePattern) => {
    setEditId(p.id);
    setName(p.name);
    const segs = Array.isArray(p.composition) && p.composition.length
      ? p.composition
      : [emptySegment()];
    setSegments(segs.map((s) => ({ charset: s.charset || 'A-Z', count: s.count || 1 })));
  };

  const save = async (asDefault = false) => {
    if (!orgId || !name.trim()) return;
    setBusy(true);
    setMessage('');
    try {
      playClick();
    } catch {
      /* ignore */
    }
    try {
      if (editId) {
        await platePatternsApi.update(orgId, editId, {
          name: name.trim(),
          mode: 'custom',
          composition: segments,
          is_default: asDefault || undefined,
        });
      } else {
        await platePatternsApi.create(orgId, {
          name: name.trim(),
          mode: 'custom',
          composition: segments,
          is_default: asDefault,
        });
      }
      resetForm();
      await load();
      setMessage(editId ? 'Composition mise à jour.' : 'Composition créée.');
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { error?: string } } })?.response?.data?.error ||
        'Échec de l’enregistrement.';
      setMessage(detail);
    } finally {
      setBusy(false);
    }
  };

  const setDefault = async (id: string) => {
    if (!orgId) return;
    setBusy(true);
    try {
      await platePatternsApi.update(orgId, id, { is_default: true });
      await load();
    } catch {
      setMessage('Impossible de marquer le défaut.');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    if (!orgId) return;
    setBusy(true);
    try {
      await platePatternsApi.delete(orgId, id);
      if (editId === id) resetForm();
      await load();
    } catch {
      setMessage('Suppression impossible.');
    } finally {
      setBusy(false);
    }
  };

  const updateSeg = (idx: number, patch: Partial<PlateSegment>) => {
    setSegments((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-cv-muted leading-relaxed">
        Compositions nommées réutilisables pour filtrer les lectures ANPR après OCR.
        Mode Standard (4–12 alphanum) reste disponible sur chaque zone ; le défaut
        organisation s’applique si la zone ne précise rien.
      </p>

      <div className="rounded-lg border border-cv-border/60 bg-cv-bg/40 p-3 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-medium text-cv-text">
            {editId ? 'Modifier la composition' : 'Nouvelle composition'}
          </h3>
          {editId && (
            <button
              type="button"
              className="text-[11px] text-cv-muted hover:text-cv-accent"
              onClick={resetForm}
            >
              Annuler
            </button>
          )}
        </div>
        <label className="block space-y-1">
          <span className="text-[11px] text-cv-muted">Nom</span>
          <input
            className="cv-input w-full text-sm"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="ex. France AA-123-AA"
          />
        </label>
        <div className="space-y-2">
          <span className="text-[11px] text-cv-muted">Segments</span>
          {segments.map((seg, idx) => (
            <div key={idx} className="flex flex-wrap items-center gap-2">
              <div className="min-w-[10rem] flex-1">
                <PremiumSelect
                  value={seg.charset}
                  onChange={(v) =>
                    updateSeg(idx, { charset: v as PlateSegment['charset'] })
                  }
                  options={CHARSETS.map((c) => ({ value: c.value, label: c.label }))}
                />
              </div>
              <input
                type="number"
                min={1}
                max={12}
                className="cv-input w-20 text-sm"
                value={seg.count}
                onChange={(e) => updateSeg(idx, { count: Number(e.target.value) || 1 })}
              />
              <button
                type="button"
                className="text-cv-muted hover:text-red-400 p-1"
                onClick={() => setSegments((prev) => prev.filter((_, i) => i !== idx))}
                disabled={segments.length <= 1}
                aria-label="Supprimer le segment"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
          <button
            type="button"
            className="inline-flex items-center gap-1 text-[11px] text-cv-accent"
            onClick={() => setSegments((prev) => [...prev, emptySegment()])}
          >
            <Plus className="w-3.5 h-3.5" /> Segment
          </button>
        </div>
        <p className="font-mono text-[11px] text-cv-muted/90 break-all">{preview}</p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="cv-btn-primary text-sm"
            disabled={busy || !name.trim()}
            onClick={() => void save(false)}
          >
            {editId ? 'Enregistrer' : 'Créer'}
          </button>
          <button
            type="button"
            className="cv-btn-secondary text-sm"
            disabled={busy || !name.trim()}
            onClick={() => void save(true)}
          >
            {editId ? 'Enregistrer comme défaut' : 'Créer comme défaut'}
          </button>
        </div>
      </div>

      {message && <p className="text-sm text-cv-muted">{message}</p>}

      {loading ? (
        <p className="text-sm text-cv-muted">Chargement…</p>
      ) : patterns.length === 0 ? (
        <p className="text-sm text-cv-muted">Aucune composition personnalisée.</p>
      ) : (
        <ul className="space-y-2">
          {patterns.map((p) => (
            <li
              key={p.id}
              className="flex flex-wrap items-start justify-between gap-2 rounded-lg border border-cv-border/50 bg-cv-panel/40 px-3 py-2"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-cv-text font-medium">{p.name}</span>
                  {p.is_default && (
                    <span className="inline-flex items-center gap-0.5 text-[10px] text-amber-400">
                      <Star className="w-3 h-3 fill-current" /> Défaut
                    </span>
                  )}
                </div>
                <p className="font-mono text-[10px] text-cv-muted break-all mt-0.5">
                  {p.mode === 'standard' ? '^[A-Z0-9]{4,12}$' : p.regex || '—'}
                </p>
              </div>
              <div className="flex items-center gap-1.5">
                {!p.is_default && (
                  <button
                    type="button"
                    className="text-[11px] text-cv-muted hover:text-amber-400 px-1.5 py-1"
                    onClick={() => void setDefault(p.id)}
                    disabled={busy}
                  >
                    Défaut
                  </button>
                )}
                <button
                  type="button"
                  className="text-[11px] text-cv-accent px-1.5 py-1"
                  onClick={() => startEdit(p)}
                >
                  Éditer
                </button>
                <button
                  type="button"
                  className="text-cv-muted hover:text-red-400 p-1"
                  onClick={() => void remove(p.id)}
                  disabled={busy}
                  aria-label="Supprimer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
