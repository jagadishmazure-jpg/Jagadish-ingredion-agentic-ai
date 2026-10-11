import { test, expect } from '../../fixtures/testFixtures';
import { getScenarios, getAgentCards, getWellKnownAgent } from '../../utils/apiClient';
import scenariosData from '../../data/scenarios.json';

test.describe('public discovery endpoints @smoke', () => {
  test('GET /api/scenarios lists all demo scenarios', async ({ api }) => {
    const res = await getScenarios(api);

    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(Array.isArray(body.scenarios)).toBe(true);
    expect(body.scenarios.length).toBeGreaterThan(0);

    const ids = body.scenarios.map((s: { id: string }) => s.id);
    for (const expected of scenariosData) {
      expect(ids, `scenario missing: ${expected.id}`).toContain(expected.id);
    }
  });

  test('GET /api/agent-cards exposes four agents with auth requirements', async ({
    api,
  }) => {
    const res = await getAgentCards(api);

    expect(res.status()).toBe(200);
    const cards = await res.json();
    for (const agent of ['rd_formulation', 'supply_chain', 'esg', 'customer_advisor']) {
      expect(cards[agent], `card missing: ${agent}`).toBeDefined();
    }
  });

  test('GET /.well-known/agent.json is the A2A discovery document', async ({ api }) => {
    const res = await getWellKnownAgent(api);

    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(Array.isArray(body.agents)).toBe(true);
    expect(body.agents.length).toBe(4);
  });
});
