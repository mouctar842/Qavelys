import { configDefaults, defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
const e2eRun = process.env.QAVELYS_E2E_RUN_ID;
const isolatedE2E = process.env.QAVELYS_E2E === '1';
if (isolatedE2E && (!e2eRun || !/^[a-zA-Z0-9_-]+$/.test(e2eRun))) throw new Error('Identifiant du cache E2E invalide.');
export default defineConfig({
  cacheDir: isolatedE2E ? `../.local/e2e-runs/${e2eRun}/vite-cache` : 'node_modules/.vite',
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/api': { target: process.env.QAVELYS_API_TARGET || 'http://127.0.0.1:8000', changeOrigin: false } } },
  test: { environment: 'jsdom', setupFiles: './src/test-setup.ts', pool: 'threads', fileParallelism: false, testTimeout: 60000, exclude: [...configDefaults.exclude, 'e2e/**'] },
});
