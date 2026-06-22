import { useEffect, useRef, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '@/stores/authStore';
import { useUiStore } from '@/stores/uiStore';
import { queryKeys } from '@/hooks/api/queries';
import { useSound } from '@/hooks/useSound';

export function useAlertWebSocket() {
  const token = useAuthStore((s) => s.token);
  const soundMuted = useUiStore((s) => s.soundMuted);
  const qc = useQueryClient();
  const { playDetection } = useSound();
  const wsRef = useRef<WebSocket | null>(null);
  const mutedRef = useRef(soundMuted);
  mutedRef.current = soundMuted;

  const connect = useCallback(() => {
    const currentToken = useAuthStore.getState().token ?? token;
    if (!currentToken) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    wsRef.current?.close();
    wsRef.current = null;

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(
      `${proto}://${window.location.host}/api/v1/ws/alerts?token=${encodeURIComponent(currentToken)}`,
    );
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data as string);
        if (data.type === 'alert') {
          if (!mutedRef.current) playDetection();
          void qc.invalidateQueries({ queryKey: queryKeys.alerts });
          void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
        }
      } catch {
        /* ignore */
      }
    };

    ws.onclose = () => {
      wsRef.current = null;
      window.setTimeout(connect, 5000);
    };
  }, [token, qc, playDetection]);

  useEffect(() => {
    connect();
    const onRefresh = () => {
      wsRef.current?.close();
      wsRef.current = null;
      connect();
    };
    window.addEventListener('cv-token-refreshed', onRefresh);
    return () => {
      window.removeEventListener('cv-token-refreshed', onRefresh);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  return null;
}
