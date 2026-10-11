/**
 * Environment resolution shared by config-adjacent code.
 * Mirrors playwright.config.ts so fixtures and specs agree on the target.
 */
const environments: Record<string, string> = {
  local: 'http://localhost:8000',
  dev: process.env.QA_DEV_URL ?? 'http://localhost:8000',
  qa: process.env.QA_QA_URL ?? 'http://localhost:8000',
};

export function resolveBaseURL(): string {
  const env = process.env.ENV ?? 'local';
  return environments[env] ?? environments.local;
}

/** Small rate-limit budget the QA service is started with (see qa/README.md). */
export function qaRateLimit(): number {
  return Number(process.env.QA_RATE_LIMIT ?? '5');
}
