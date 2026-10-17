import { defineConfig, devices } from '@playwright/test';

/**
 * Multi-environment configuration.
 * Usage:  ENV=local npx playwright test   (default)
 *         ENV=qa    npx playwright test
 *         ENV=dev   npx playwright test
 *
 * Required env for authenticated tests: QA_TOKEN (mint with
 * `python -m food_ingredients_ai.service.mint_token --scopes formulation:write,supply:read,esg:read,proposal:read`)
 * Optional: QA_TOKEN_READONLY, QA_TOKEN_RATELIMIT, QA_RATE_LIMIT.
 */
const environments: Record<string, { baseURL: string }> = {
  local: { baseURL: 'http://localhost:8000' },
  dev: { baseURL: process.env.QA_DEV_URL ?? 'http://localhost:8000' },
  qa: { baseURL: process.env.QA_QA_URL ?? 'http://localhost:8000' },
};

const env = process.env.ENV ?? 'local';
const baseURL = environments[env]?.baseURL ?? environments.local.baseURL;

export default defineConfig({
  testDir: './tests',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI
    ? [['list'], ['junit', { outputFile: 'results.xml' }], ['html', { open: 'never' }]]
    : [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
});
