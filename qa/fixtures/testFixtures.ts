import { test as base, request, APIRequestContext } from '@playwright/test';
import { DemoPage } from '../pages/DemoPage';
import { resolveBaseURL } from '../utils/env';
import { mintToken, uniqueSubject, FULL_SCOPES, READONLY_SCOPES } from '../utils/tokens';

/**
 * Shared fixtures: API contexts (anonymous + authenticated) and page objects.
 * Tokens are minted per test via the service's own CLI (synthetic JWTs —
 * no secrets). Set QA_TOKEN / QA_TOKEN_READONLY / QA_TOKEN_RATELIMIT to
 * override minting with pre-made tokens.
 */

type Fixtures = {
  api: APIRequestContext;
  authApi: APIRequestContext;
  tokens: { full: string; readOnly: string; rateLimit: string };
  demoPage: DemoPage;
};

async function newApiContext(extraHeaders: Record<string, string> = {}) {
  return request.newContext({
    baseURL: resolveBaseURL(),
    extraHTTPHeaders: extraHeaders,
  });
}

export const test = base.extend<Fixtures>({
  api: async ({}, use) => {
    const ctx = await newApiContext();
    await use(ctx);
    await ctx.dispose();
  },
  tokens: async ({}, use) => {
    // Per-test unique subjects → each test gets its own rate-limit budget.
    // Env overrides exist for exotic setups; default is self-minting.
    await use({
      full:
        process.env.QA_TOKEN ??
        mintToken(uniqueSubject('qa-full'), FULL_SCOPES),
      readOnly:
        process.env.QA_TOKEN_READONLY ??
        mintToken(uniqueSubject('qa-readonly'), READONLY_SCOPES),
      rateLimit:
        process.env.QA_TOKEN_RATELIMIT ??
        mintToken(uniqueSubject('qa-ratelimit'), 'formulation:write'),
    });
  },
  authApi: async ({ tokens }, use) => {
    const ctx = await newApiContext({ Authorization: `Bearer ${tokens.full}` });
    await use(ctx);
    await ctx.dispose();
  },
  demoPage: async ({ page }, use) => {
    await use(new DemoPage(page));
  },
});

export { expect } from '@playwright/test';
