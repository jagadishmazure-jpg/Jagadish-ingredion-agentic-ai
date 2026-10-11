import { test, expect } from '../../fixtures/testFixtures';
import { postReformulate } from '../../utils/apiClient';
import { DEFAULT_SCENARIO } from '../../utils/testData';

test.describe('authentication & authorization @smoke', () => {
  test('missing token → 401', async ({ api }) => {
    const res = await postReformulate(api, { scenario: DEFAULT_SCENARIO });

    expect(res.status()).toBe(401);
    expect(res.headers()['www-authenticate']).toContain('Bearer');
  });

  test('malformed token → 401', async ({ api }) => {
    const res = await api.post('/api/reformulate', {
      data: { scenario: DEFAULT_SCENARIO },
      headers: { Authorization: 'Bearer not-a-real-token' },
    });

    expect(res.status()).toBe(401);
  });

  test('valid token without formulation:write → 403', async ({ api, tokens }) => {
    // QA_TOKEN_READONLY carries only supply:read — reformulate needs formulation:write.
    const res = await api.post('/api/reformulate', {
      data: { scenario: DEFAULT_SCENARIO },
      headers: { Authorization: `Bearer ${tokens.readOnly}` },
    });

    expect(res.status()).toBe(403);
  });

  test('read-only token CAN run the supply agent (scope isolation)', async ({
    api,
    tokens,
  }) => {
    const res = await api.post('/api/agents/supply_chain/run', {
      data: { message: 'Forecast demand', formula_id: 'sweet_bakery_cake', region: 'NA' },
      headers: { Authorization: `Bearer ${tokens.readOnly}` },
    });

    expect(res.status()).toBe(200);
    expect((await res.json()).agent).toBe('supply_chain');
  });
});
