# Playwright QA — API + UI end-to-end tests

TypeScript Playwright framework for the agent service (`food_ingredients_ai/service/`)
and the demo UI (`GET /`). Follows the repo's QA guides: Page Object Model,
fixtures, test data separated from logic, multi-environment config, API+UI
integration, parallel execution, and CI-friendly reporting.

## Layout

```
qa/
├── pages/          # Page Object Model (DemoPage — business-level methods)
├── fixtures/       # test.extend() fixtures (api, authApi, tokens, demoPage)
├── utils/          # apiClient.ts (typed client), assertions.ts (custom matcher),
│                   # env.ts, testData.ts
├── data/           # scenarios.json, agents.csv (no secrets — tokens via env)
├── tests/api/      # health, discovery, reformulate, agents (CSV-driven),
│                   # auth (401/403), reliability (429)
└── tests/ui/       # demo.spec.ts (POM + test.step + AAA)
```

## Quickstart

```bash
# 1. Start the service (from the repo root). Use a small rate-limit budget
#    so the 429 test runs fast; default 60/min otherwise.
cd ~/workspace/github-scaffolds/Jagadish-food-ingredients-agentic-ai
SERVICE_RATE_LIMIT_PER_MIN=5 \
  ~/.venvs/qav/bin/python -m uvicorn food_ingredients_ai.service.app:app --port 8000 &

# 2. Point the framework at a Python with the service deps installed.
#    Tokens are minted automatically per test (unique subjects → isolated
#    rate-limit budgets). Override only if you must:
#      QA_TOKEN / QA_TOKEN_READONLY / QA_TOKEN_RATELIMIT
export QA_PYTHON=~/.venvs/qav/bin/python   # or: python3 with deps installed
export QA_RATE_LIMIT=5   # must match SERVICE_RATE_LIMIT_PER_MIN above

# 3. Install + run
cd qa && npm install
npx playwright test --project=chromium            # fast lane
npx playwright test                               # all browsers (chromium/firefox/webkit)
ENV=qa npx playwright test --project=chromium     # against another environment
```

## Conventions

- **AAA** (Arrange-Act-Assert) with `test.step()` in every test — the HTML report
  reads as a structured story.
- **Locators**: prefer `getByRole`/`getByLabel`/`getByTestId`; the UI exposes
  stable ids (`#scenario-select`, `#token-input`, `#run-button`, `#results`, `#status`).
- **No `waitForTimeout`** — wait for conditions (web-first assertions, `waitForFunction`).
- **API-first setup**: specs create state via API, UI asserts user-facing behavior.
- **Tags**: `@smoke` (health, auth, discovery) vs `@regression` — `npx playwright test --grep @smoke`.

## Tooling notes

- Record a flow: `npx playwright codegen http://localhost:8000` — then refactor
  the output into `pages/` (never commit raw codegen).
- Debug: `npx playwright test --debug`; inspect failures with
  `npx playwright show-report` (traces/screenshots/video are kept on failure).
- Sharding in CI: `npx playwright test --shard=1/2` (blob report + merge-reports
  for multi-machine runs).
