import { defineConfig, devices } from '@playwright/test';

const PORT = Number(process.env.E2E_PORT ?? 4401);
const ORIGIN = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: 'tests',
  testMatch: /.*\.spec\.ts/,
  timeout: 90_000,
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  // Snapshots live next to the tests, one folder per spec file (allowed in git, CLAUDE.md section 7).
  snapshotPathTemplate: '{testDir}/__screenshots__/{testFilePath}/{arg}{ext}',
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.01, animations: 'disabled' } },
  use: { baseURL: `${ORIGIN}/GH-Breakout/`, ...devices['Desktop Chrome'] },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // Serves the fixture build (npm run build:fx).
  webServer: {
    command: `npx astro preview --port ${PORT} --host 127.0.0.1`,
    url: `${ORIGIN}/GH-Breakout/`,
    reuseExistingServer: !process.env.CI,
    env: { OUT_DIR: 'dist-fx' },
    timeout: 60_000,
  },
});
