import { useEffect } from 'react';
import { authApi } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import { useCameras } from '@/hooks/api/queries';

/** Remplit siteId après login si absent (zones, caméras). */
export function useEnsureSiteId() {
  const orgId = useAuthStore((s) => s.orgId);
  const siteId = useAuthStore((s) => s.siteId);
  const setSiteId = useAuthStore((s) => s.setSiteId);
  const cameras = useCameras();

  useEffect(() => {
    if (siteId || !orgId) return;

    const cam = cameras.data?.[0];
    if (cam?.siteId) {
      setSiteId(cam.siteId);
      return;
    }

    void authApi.me().then(({ data }) => {
      if (data.site_id) setSiteId(data.site_id);
    }).catch(() => {
      /* ignore */
    });
  }, [siteId, orgId, cameras.data, setSiteId]);
}
