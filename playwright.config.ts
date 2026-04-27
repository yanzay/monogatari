import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for Monogatari E2E.
 *
 * The app is fully static; we serve it via `vite preview` over the
 * production build at /monogatari/ to mirror the GH Pages deployment.
 */
const PORT = 4178;

export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}/monogatari/`,
    trace: 'on-first-retry',
    video: process.env.CI ? 'retain-on-failure' : 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: `npx vite preview --port ${PORT} --host 127.0.0.1 --strictPort`,
    url: `http://127.0.0.1:${PORT}/monogatari/`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
