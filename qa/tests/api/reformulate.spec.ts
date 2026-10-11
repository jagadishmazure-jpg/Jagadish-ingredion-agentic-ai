import Ajv from 'ajv';
import { test } from '../../fixtures/testFixtures';
import { expect } from '../../utils/assertions';
import { postReformulate, timed } from '../../utils/apiClient';
import { DEFAULT_SCENARIO, UNKNOWN_SCENARIO } from '../../utils/testData';

/** JSON-schema validation (ajv) for the reformulate response contract. */
const reformulateSchema = {
  type: 'object',
  required: ['session_id', 'elapsed_ms', 'blackboard', 'scenario'],
  properties: {
    session_id: { type: 'string', minLength: 1 },
    elapsed_ms: { type: 'number' },
    scenario: { type: 'string' },
    blackboard: { type: 'object' },
    grounding: { type: 'array' },
    degraded: { type: 'boolean' },
  },
  additionalProperties: true,
};

const ajv = new Ajv({ allErrors: true });
const validateReformulate = ajv.compile(reformulateSchema);

test.describe('POST /api/reformulate @regression', () => {
  test('happy path returns a valid reformulation (AAA)', async ({ authApi }) => {
    // Arrange
    const body = { scenario: DEFAULT_SCENARIO };

    // Act
    const { res, ms } = await timed(() => postReformulate(authApi, body));

    // Assert
    expect(res.status()).toBe(200);
    expect(ms).toBeLessThan(60_000);
    const responseBody = await res.json();
    expect(validateReformulate(responseBody)).toBe(true);
    expect(responseBody).toBeValidReformulationResponse();
    expect(responseBody.scenario).toBe(DEFAULT_SCENARIO);
    // Business outcome: the workflow flagged non-clean-label ingredients.
    const analysis = responseBody.blackboard.analyze_ingredients ?? {};
    expect(analysis.flagged_count ?? 0).toBeGreaterThan(0);
  });

  test('unknown scenario is rejected with 400', async ({ authApi }) => {
    const res = await postReformulate(authApi, { scenario: UNKNOWN_SCENARIO });

    expect(res.status()).toBe(400);
  });

  test('idempotency key replays the stored response', async ({ authApi }) => {
    const key = `qa-reformulate-${Date.now()}`;
    const headers = { 'Idempotency-Key': key };

    const first = await postReformulate(authApi, { scenario: DEFAULT_SCENARIO }, headers);
    expect(first.status()).toBe(200);
    const firstBody = await first.json();

    const second = await postReformulate(authApi, { scenario: DEFAULT_SCENARIO }, headers);
    expect(second.status()).toBe(200);
    const secondBody = await second.json();

    // Replay must be byte-identical to the original response.
    expect(secondBody).toEqual(firstBody);
  });

  test('response carries a session id header', async ({ authApi }) => {
    const res = await postReformulate(authApi, { scenario: DEFAULT_SCENARIO });

    expect(res.status()).toBe(200);
    expect(res.headers()['x-session-id']).toBeTruthy();
  });
});
