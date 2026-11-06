import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Vitest settings: run component tests in a simulated browser (jsdom).
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
  },
  server: {
    // Listen on all interfaces so the dev server works inside containers /
    // remote previews, not only on "localhost".
    host: '0.0.0.0',
    port: 5173,
    // Accept any Host header (needed when the dev server is reached through
    // a proxy or a preview URL instead of plain localhost).
    allowedHosts: true,
    // Dev-server proxy: any browser request that starts with /api is
    // forwarded to the Flask backend. The React code can therefore call
    // fetch('/api/...') with a relative URL and never needs to know where
    // the backend lives. The proxy runs server-side, so "localhost" here
    // means "the machine running Vite", which is also running Flask.
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    },
  },
})
