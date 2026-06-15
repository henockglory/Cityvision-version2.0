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
      },
      '/health': {
        target: 'http://localhost:8081',
        changeOrigin: true,
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
    },
  },
});
