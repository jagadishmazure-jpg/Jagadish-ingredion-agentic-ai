import { Locator, Page } from '@playwright/test';

/**
 * Page Object Model for the demo UI (GET /).
 * Business-level methods only — specs never touch raw locators.
 * Stable element ids: #scenario-select, #token-input, #run-button,
 * #results, #status, #raw-json.
 */
export class DemoPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly scenarioSelect: Locator;
  readonly tokenInput: Locator;
  readonly runButton: Locator;
  readonly status: Locator;
  readonly results: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: 'Clean-Label Reformulation Demo' });
    this.scenarioSelect = page.locator('#scenario-select');
    this.tokenInput = page.locator('#token-input');
    this.runButton = page.locator('#run-button');
    this.status = page.locator('#status');
    this.results = page.locator('#results');
  }

  async goto() {
    await this.page.goto('/');
    await this.heading.waitFor();
  }

  /** Wait until the scenario dropdown is populated from /api/scenarios. */
  async waitForScenarios() {
    await this.page.waitForFunction(
      () => document.querySelectorAll('#scenario-select option').length > 0,
    );
  }

  async scenarioOptions(): Promise<string[]> {
    return this.scenarioSelect.locator('option').allTextContents();
  }

  async selectScenario(scenarioId: string) {
    await this.scenarioSelect.selectOption(scenarioId);
  }

  async fillToken(token: string) {
    await this.tokenInput.fill(token);
  }

  async runReformulation() {
    await this.runButton.click();
  }

  /** Full business workflow: pick a scenario, authenticate, run, wait for results. */
  async runScenario(scenarioId: string, token: string) {
    await this.goto();
    await this.waitForScenarios();
    await this.selectScenario(scenarioId);
    await this.fillToken(token);
    await this.runReformulation();
    await this.results.locator('h2', { hasText: 'Results' }).waitFor({ timeout: 60_000 });
  }

  async statusText(): Promise<string> {
    return (await this.status.textContent()) ?? '';
  }

  async resultsText(): Promise<string> {
    return (await this.results.textContent()) ?? '';
  }
}
