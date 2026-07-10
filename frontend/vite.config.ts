import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [react()],
  define: {
    'import.meta.env.VITE_BUILD_ID': JSON.stringify(
      process.env.VITE_BUILD_ID ?? `v2.2-${new Date().toISOString().slice(0, 10)}`,
    ),
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@shared': fileURLToPath(new URL('../shared', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://localhost:8081',
        changeOrigin: true,
        ws: true,
        timeout: 0,
        // Large demo MP4 uploads (up to ~500 Mo) — align with uploadVideo axios timeout (50 min).
        proxyTimeout: 3_000_000,
      },
      '/health': {
        target: 'http://localhost:8081',
        changeOrigin: true,
        timeout: 0,
        proxyTimeout: 30_000,
      },
      '/go2rtc': {
        target: 'http://localhost:1984',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/go2rtc/, ''),
      },
      '/ai-engine': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/ai-engine/, ''),
      },
      '/rules-engine': {
        target: 'http://localhost:8010',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/rules-engine/, ''),
      },
      '/frigate': {
        target: process.env.VITE_FRIGATE_URL || 'http://127.0.0.1:5000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/frigate/, ''),
      },
      '/frigate-go2rtc': {
        target: process.env.VITE_FRIGATE_GO2RTC_URL || 'http://127.0.0.1:8557',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/frigate-go2rtc/, ''),
      },
    },
  },
});
