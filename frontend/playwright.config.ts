import { defineConfig } from '@playwright/test';
import path from 'node:path';

if (process.env.QAVELYS_E2E !== '1' || !process.env.POSTGRES_DB?.startsWith('qavelys_e2e_')) throw new Error('Utiliser infrastructure/e2e.ps1 avec une base E2E dédiée.');
const runId = process.env.QAVELYS_E2E_RUN_ID;
if (!runId || !/^[a-zA-Z0-9_-]+$/.test(runId)) throw new Error('Identifiant E2E invalide.');
const frontendPort = Number(process.env.QAVELYS_E2E_FRONTEND_PORT || '5174');
const backendPort = Number(process.env.QAVELYS_E2E_BACKEND_PORT || '8001');
const output = path.resolve('..', '.local', 'e2e-runs', runId);
export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1, retries: 0, timeout: 1_200_000,
  expect: { timeout: 60_000 }, outputDir: path.join(output, 'artifacts'),
  reporter: [['list'], ['html', { outputFolder: path.join(output, 'report'), open: 'never' }]],
  use: { baseURL: `http://127.0.0.1:${frontendPort}`, browserName: 'chromium', channel: 'chromium', viewport: { width: 1440, height: 1000 }, actionTimeout: 60_000, navigationTimeout: 60_000, trace: 'retain-on-failure', screenshot: 'only-on-failure', video: 'off' },
  webServer: [
    { command: `"${path.resolve('..', '.venv', 'Scripts', 'python.exe')}" "${path.resolve('..', 'backend', 'manage.py')}" runserver 127.0.0.1:${backendPort} --noreload`, url: `http://127.0.0.1:${backendPort}/api/v1/auth/csrf/`, reuseExistingServer: false, timeout: 90_000 },
    { command: `npm run dev -- --port ${frontendPort} --strictPort`, url: `http://127.0.0.1:${frontendPort}`, env: { QAVELYS_API_TARGET: `http://127.0.0.1:${backendPort}` }, reuseExistingServer: false, timeout: 90_000 },
  ],
});
