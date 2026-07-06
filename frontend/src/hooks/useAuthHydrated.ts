import { useEffect, useState } from 'react';
import { useAuthStore } from '@/stores/authStore';

/** Wait for persisted auth before routing decisions (avoids flash redirect to /login). */
export function useAuthHydrated(): boolean {
  const [hydrated, setHydrated] = useState(() => useAuthStore.persist.hasHydrated());

  useEffect(() => {
    if (useAuthStore.persist.hasHydrated()) {
      setHydrated(true);
      return;
    }
    const unsub = useAuthStore.persist.onFinishHydration(() => setHydrated(true));
    void useAuthStore.persist.rehydrate();
    return unsub;
  }, []);

  return hydrated;
}
