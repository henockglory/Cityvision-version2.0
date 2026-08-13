const DB_NAME = 'cv-alert-sounds';
const STORE = 'sounds';
const DB_VERSION = 1;

export type CustomAlertSoundMeta = {
  id: string;
  name: string;
  mime: string;
  createdAt: number;
  size: number;
};

type CustomAlertSoundRecord = CustomAlertSoundMeta & {
  blob: Blob;
};

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'id' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('indexedDB open failed'));
  });
}

function txDone(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error ?? new Error('indexedDB tx failed'));
    tx.onabort = () => reject(tx.error ?? new Error('indexedDB tx aborted'));
  });
}

function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `c-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export async function listCustomAlertSounds(): Promise<CustomAlertSoundMeta[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly');
    const store = tx.objectStore(STORE);
    const req = store.getAll();
    req.onsuccess = () => {
      const rows = (req.result as CustomAlertSoundRecord[]).map(({ id, name, mime, createdAt, size }) => ({
        id,
        name,
        mime,
        createdAt,
        size,
      }));
      rows.sort((a, b) => b.createdAt - a.createdAt);
      resolve(rows);
    };
    req.onerror = () => reject(req.error ?? new Error('list failed'));
  });
}

export async function getCustomAlertSoundBlob(id: string): Promise<Blob | null> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).get(id);
    req.onsuccess = () => {
      const row = req.result as CustomAlertSoundRecord | undefined;
      resolve(row?.blob ?? null);
    };
    req.onerror = () => reject(req.error ?? new Error('get failed'));
  });
}

export async function addCustomAlertSound(file: File): Promise<CustomAlertSoundMeta> {
  const id = newId();
  const record: CustomAlertSoundRecord = {
    id,
    name: file.name || `audio-${id}`,
    mime: file.type || 'application/octet-stream',
    createdAt: Date.now(),
    size: file.size,
    blob: file,
  };
  const db = await openDb();
  const tx = db.transaction(STORE, 'readwrite');
  tx.objectStore(STORE).put(record);
  await txDone(tx);
  return {
    id: record.id,
    name: record.name,
    mime: record.mime,
    createdAt: record.createdAt,
    size: record.size,
  };
}

export async function deleteCustomAlertSound(id: string): Promise<void> {
  const db = await openDb();
  const tx = db.transaction(STORE, 'readwrite');
  tx.objectStore(STORE).delete(id);
  await txDone(tx);
}

export async function playCustomAlertSound(id: string, volume: number): Promise<void> {
  const blob = await getCustomAlertSoundBlob(id);
  if (!blob) throw new Error('custom sound not found');
  const url = URL.createObjectURL(blob);
  try {
    await playAudioUrl(url, volume);
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function playAudioUrl(src: string, volume: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const audio = new Audio(src);
    audio.volume = Math.max(0, Math.min(1, volume));
    const cleanup = () => {
      audio.onended = null;
      audio.onerror = null;
    };
    audio.onended = () => {
      cleanup();
      resolve();
    };
    audio.onerror = () => {
      cleanup();
      reject(new Error('audio play failed'));
    };
    void audio.play().catch((err: unknown) => {
      cleanup();
      reject(err instanceof Error ? err : new Error(String(err)));
    });
  });
}
