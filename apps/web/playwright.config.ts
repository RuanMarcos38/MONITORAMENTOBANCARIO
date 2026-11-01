import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  retries: 0,
  use: { baseURL: 'http://localhost:3000', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  reporter: [['list'], ['html', { open: 'never' }]],
  webServer: [
    { command: 'python -m uvicorn app.main:app --port 8000', cwd: '../api', url: 'http://localhost:8000/api/v1/health', reuseExistingServer: false, timeout: 90000 },
    { command: 'pnpm dev --hostname 0.0.0.0 --port 3000', url: 'http://localhost:3000', reuseExistingServer: false, timeout: 120000 },
  ],
});
