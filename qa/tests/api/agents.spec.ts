import { readFileSync } from 'fs';
import { join } from 'path';
import { parse } from 'csv-parse/sync';
import { test, expect } from '../../fixtures/testFixtures';
import { postAgentRun } from '../../utils/apiClient';

/**
 * CSV data-driven test: one row per agent (agent, scope, message).
 * The token used here must carry all four agent scopes.
 */
interface AgentRow {
  agent: string;
  scope: string;
  message: string;
}

const rows = parse(
  readFileSync(join(__dirname, '../../data/agents.csv'), 'utf-8'),
  { columns: true, skip_empty_lines: true, trim: true },
) as AgentRow[];

test.describe('POST /api/agents/{agent}/run (data-driven) @regression', () => {
  for (const row of rows) {
    test(`${row.agent} runs and reports its skill`, async ({ authApi }) => {
      // Arrange
      const body = {
        message: row.message,
        formula_id: 'sweet_bakery_cake',
        region: 'NA',
      };

      // Act
      const res = await postAgentRun(authApi, row.agent, body);

      // Assert
      expect(res.status()).toBe(200);
      const responseBody = await res.json();
      expect(responseBody.agent).toBe(row.agent);
      expect(responseBody.session_id).toBeTruthy();
    });
  }
});
