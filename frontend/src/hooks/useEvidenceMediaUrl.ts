import { useEffect, useRef, useState } from 'react';
import type { AxiosError } from 'axios';
import api from '@/api/client';

const API_V1_PREFIX = '/api/v1/';

/** Strip /api/v1 so path is relative to axios baseURL (/api/v1). */
export function toRelativeEvidencePath(url: string): string {
  if (!url) return url;
  try {
    let path = url;
    if (!path.startsWith('/') && !path.startsWith('http')) {
      return path;
    }
    if (path.startsWith('http')) {
      const parsed = new URL(path);
      path = parsed.pathname + parsed.search;
    }
    const idx = path.indexOf(API_V1_PREFIX);
    if (idx >= 0) {
      return path.slice(idx + API_V1_PREFIX.length);
    }
    if (path.startsWith('/orgs/')) {
      return path.slice(1);
    }
    return path.replace(/^\//, '');
  } catch {
    /* ignore */
  }
  return url;
}

export interface EvidenceMediaState {
  blobUrl: string | undefined;
  loading: boolean;
  error: boolean;
}

function blobFromResponse(res: { data: Blob; headers: Record<string, unknown> }, fallbackType?: string): Blob {
  const raw = res.data as Blob;
  const ct =
    (typeof res.headers['content-type'] === 'string' ? res.headers['content-type'] : undefined) ||
    fallbackType ||
    raw.type;
  if (ct && (!raw.type || raw.type === 'application/octet-stream')) {
    return new Blob([raw], { type: ct.split(';')[0].trim() });
  }
  return raw;
}

export function useEvidenceMediaUrl(
  apiUrl: string | undefined,
  options?: { mimeFallback?: string; retryKey?: number },
): EvidenceMediaState {
  const [blobUrl, setBlobUrl] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const revokeRef = useRef<string | undefined>();

  useEffect(() => {
    if (!apiUrl) {
      setBlobUrl(undefined);
      setLoading(false);
      setError(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(false);

    const path = toRelativeEvidencePath(apiUrl);
    api
      .get(path, { responseType: 'blob' })
      .then((res) => {
        if (cancelled) return;
        const blob = blobFromResponse(res, options?.mimeFallback);
        const url = URL.createObjectURL(blob);
        if (revokeRef.current) URL.revokeObjectURL(revokeRef.current);
        revokeRef.current = url;
        setBlobUrl(url);
        setLoading(false);
      })
      .catch((err: AxiosError) => {
        if (cancelled) return;
        if (import.meta.env.DEV) {
          console.warn('[evidence] media fetch failed', {
            path,
            status: err.response?.status,
            message: err.message,
          });
        }
        setError(true);
        setLoading(false);
        setBlobUrl(undefined);
      });

    return () => {
      cancelled = true;
    };
  }, [apiUrl, options?.mimeFallback, options?.retryKey]);

  useEffect(() => {
    return () => {
      if (revokeRef.current) {
        URL.revokeObjectURL(revokeRef.current);
        revokeRef.current = undefined;
      }
    };
  }, []);

  return { blobUrl, loading, error };
}
