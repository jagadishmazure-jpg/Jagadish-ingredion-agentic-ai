import { test, expect } from '../../fixtures/testFixtures';
import { DEFAULT_SCENARIO } from '../../utils/testData';

/**
 * UI tests drive the demo page through the Page Object Model.
 * Convention: test.step() + AAA (Arrange-Act-Assert) in every test.
 */
test.describe('demo UI @regression', () => {
  test('page loads with banner, scenario picker and run controls', async ({
    demoPage,
  }) => {
    await test.step('Arrange: open the demo page', async () => {
      await demoPage.goto();
    });

    await test.step('Assert: key controls are visible', async () => {
      await expect(demoPage.heading).toBeVisible();
      await expect(demoPage.scenarioSelect).toBeVisible();
      await expect(demoPage.tokenInput).toBeVisible();
      await expect(demoPage.runButton).toBeEnabled();
    });

    await test.step('Assert: scenarios load from the API', async () => {
      await demoPage.waitForScenarios();
      const options = await demoPage.scenarioOptions();
      expect(options.length).toBeGreaterThan(0);
      expect(options.join(' ')).toContain(DEFAULT_SCENARIO);
    });
  });

  test('running a scenario renders the 5-step reformulation results', async ({
    demoPage,
    tokens,
  }) => {
    await test.step('Arrange: pick scenario and authenticate', async () => {
      await demoPage.goto();
      await demoPage.waitForScenarios();
      await demoPage.selectScenario(DEFAULT_SCENARIO);
      await demoPage.fillToken(tokens.full);
    });

    await test.step('Act: run the reformulation', async () => {
      await demoPage.runReformulation();
    });

    await test.step('Assert: results render', async () => {
      await expect(demoPage.results.locator('h2')).toContainText('Results', {
        timeout: 60_000,
      });
      const text = await demoPage.resultsText();
      expect(text).toContain('Flagged ingredients');
      expect(text).toContain('Substitutions');
      expect(text).toContain('Claim validation');
      const status = await demoPage.statusText();
      expect(status).toContain('Done in');
    });
  });

  test('missing token shows a helpful message instead of calling the API', async ({
    demoPage,
  }) => {
    await test.step('Arrange: pick a scenario but no token', async () => {
      await demoPage.goto();
      await demoPage.waitForScenarios();
      await demoPage.selectScenario(DEFAULT_SCENARIO);
    });

    await test.step('Act: click run without a token', async () => {
      await demoPage.runReformulation();
    });

    await test.step('Assert: guidance is shown', async () => {
      await expect(demoPage.status).toContainText('demo bearer token', {
        timeout: 10_000,
      });
    });
  });
});
