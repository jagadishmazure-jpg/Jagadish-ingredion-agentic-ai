import { test, expect } from '../../fixtures/testFixtures';
import { getHealth, timed } from '../../utils/apiClient';
import { EXPECTED_HEALTH_FIELDS } from '../../utils/testData';

test.describe('service health @smoke', () => {
  test('GET /api/health returns ok with service metadata', async ({ api }) => {
    // Arrange / Act
    const { res, ms } = await timed(() => getHealth(api));

    // Assert
    expect(res.status()).toBe(200);
    expect(ms).toBeLessThan(2000); // response-time assertion
    const body = await res.json();
    for (const field of EXPECTED_HEALTH_FIELDS) {
      expect(body[field], `missing field: ${field}`).toBeDefined();
    }
    expect(body.status).toBe('ok');
  });

  test('service becomes ready via polling', async ({ api }) => {
    // expect.poll retries until the service answers — useful in CI startup races.
    await expect
      .poll(async () => (await getHealth(api)).status(), {
        message: 'service did not become ready',
        timeout: 30_000,
      })
      .toBe(200);
  });
});
