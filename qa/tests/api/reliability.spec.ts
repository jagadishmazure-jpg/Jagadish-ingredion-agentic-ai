import { test, expect } from '../../fixtures/testFixtures';
import { postReformulate } from '../../utils/apiClient';
import { DEFAULT_SCENARIO } from '../../utils/testData';
import { qaRateLimit } from '../../utils/env';

/**
 * Rate limiting (429). Requires the service to run with a small budget:
 *   SERVICE_RATE_LIMIT_PER_MIN=5 uvicorn ...   (see qa/README.md)
 * The limiter is keyed by token subject, so QA_TOKEN_RATELIMIT (dedicated
 * subject) keeps this test isolated from every other spec.
 */
test.describe('rate limiting', () => {
  test('exceeding the per-minute budget → 429 with Retry-After', async ({
    api,
    tokens,
  }) => {
    test.skip(
      process.env.QA_RATE_LIMIT !== '5',
      'needs QA_RATE_LIMIT=5 and SERVICE_RATE_LIMIT_PER_MIN=5 (see qa/README.md)',
    );
    const limit = qaRateLimit();
    const headers = { Authorization: `Bearer ${tokens.rateLimit}` };

    let lastStatus = 0;
    let retryAfter: string | undefined;
    for (let i = 0; i < limit + 1; i++) {
      const res = await api.post('/api/reformulate', {
        data: { scenario: DEFAULT_SCENARIO },
        headers,
      });
      lastStatus = res.status();
      retryAfter = res.headers()['retry-after'];
      // 403 would mean the token lacks scope — a setup error, not a rate limit.
      expect(lastStatus, `unexpected status on attempt ${i + 1}`).not.toBe(403);
      if (lastStatus === 429) break;
    }

    expect(lastStatus).toBe(429);
    expect(retryAfter, 'Retry-After header').toBeTruthy();
  });
});
