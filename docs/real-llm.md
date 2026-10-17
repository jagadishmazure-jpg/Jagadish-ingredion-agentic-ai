# Going Live with a Real LLM

Everything in this repo runs **offline by default**: the test suite, the
demo service, and all four business-flow graphs use a scripted
`FakeChatClient` — deterministic, free, no API keys. This guide covers
switching to a **real LLM** for live demos.

## The two live paths

`build_chat_client(live=True)` picks a provider in this order:

| # | Provider | Needs | Best for |
|---|----------|-------|----------|
| 1 | **Direct OpenAI** | `OPENAI_API_KEY` only | Learning, demos, personal key |
| 2 | **Azure OpenAI** | `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_CHAT_DEPLOYMENT` (+ key or Azure login) | Enterprise, private networking, Foundry |

If `OPENAI_API_KEY` is set, direct OpenAI wins — you do **not** need any
Azure resource for path 1.

## Quickstart: direct OpenAI (recommended first step)

1. Get a key at <https://platform.openai.com/api-keys>.
2. Copy `.env.example` to `.env` and set:
   ```bash
   OPENAI_API_KEY=<redacted>
   # optional: OPENAI_MODEL=gpt-4o-mini   # cheaper/faster than gpt-4o
   ```
   Never commit `.env` — it is git-ignored.
3. Or export directly (no file):
   ```bash
   export OPENAI_API_KEY=<redacted>
   export OPENAI_MODEL=gpt-4o-mini
   ```
4. Build the client in code:
   ```python
   from food_ingredients_ai.framework.clients import build_chat_client
   client = build_chat_client(live=True)   # direct OpenAI, model gpt-4o-mini
   ```

## Cost warning

**Live calls cost real money.** Every agent turn sends your prompt *and*
the assembled context (RAG chunks, tool schemas, history) to the model,
and you pay per token in both directions. The offline fakes exist
precisely so development and CI stay free.

Cost hygiene for live runs:

- Start with `gpt-4o-mini` (much cheaper than `gpt-4o`) until prompts are stable.
- Keep the context budget tight — see `food_ingredients_ai/context/budget.py`.
- Watch `food_ingredients_ai/observability/costs.py`: token/cost attribution per agent.
- Set a billing limit / alert in your OpenAI account dashboard.
- Never run the full test suite in live mode — tests are written for fakes.

## Keep tests on fakes

The deterministic suite (`pytest -q`) must keep passing with **no keys
set**. Live mode is for interactive demos and exploration only:

- `build_chat_client(live=False)` raises on purpose — offline code must
  construct `FakeChatClient` with an explicit script.
- `build_chat_client(live=True)` with no provider configured raises a
  `RuntimeError` telling you exactly which variables are missing.

## Azure OpenAI path (when you outgrow a personal key)

Unset `OPENAI_API_KEY`, then fill in the Azure block of `.env`:

```bash
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT=<your deployment name>
# optional: AZURE_OPENAI_API_KEY=<redacted>  (else DefaultAzureCredential: az login / managed identity)
```

This is the path the Terraform (`infra/terraform/`) and the AKS
enterprise deployment target.
