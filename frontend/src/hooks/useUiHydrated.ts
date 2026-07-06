import { useEffect, useState } from 'react';
import { useUiStore } from '@/stores/uiStore';

/** Wait for persisted UI preferences before applying volatile defaults (e.g. demo camera). */
export function useUiHydrated(): boolean {
  const [hydrated, setHydrated] = useState(() => useUiStore.persist.hasHydrated());

  useEffect(() => {
    if (useUiStore.persist.hasHydrated()) {
      setHydrated(true);
      return;
    }
    const unsub = useUiStore.persist.onFinishHydration(() => setHydrated(true));
    void useUiStore.persist.rehydrate();
    return unsub;
  }, []);

  return hydrated;
}
