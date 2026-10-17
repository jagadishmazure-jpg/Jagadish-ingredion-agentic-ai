# Interview points

## The 30-second version

Four domain agents on Microsoft Agent Framework 1.0 for a fictional
food-ingredients manufacturer. The R&D agent runs a fixed tool sequence, then
supply chain, ESG and customer agents fan out in parallel. Everything is
deterministic offline with a scripted chat client, and the same agents run
against Azure OpenAI by swapping one client.

## Points to make

1. **Agents that can say no.** The claim validator rejects "natural" while
   refined sugar remains: 2 of 3 claims pass in the headline run.
2. **Determinism for testing.** A scripted `FakeChatClient` implements the
   framework's chat client interface, so 687 tests and the eval suite (20/20)
   run with no keys. Live mode is one client swap.
3. **Governance in the path, not beside it.** Scoped tokens per skill, a policy
   engine, human approval gates and a hash-chained audit log.
4. **Graceful degradation.** If the live model fails, the service returns the
   offline result with `degraded: true` instead of an error.
5. **Production path is real code, not slides.** Terraform validates in CI,
   Kubernetes manifests, a Playwright API/UI suite against the running service.
6. **Honesty.** Every heuristic and number is labelled synthetic or a demo
   assumption, and nothing is claimed as deployed.

## Likely follow-ups

- *Why Agent Framework rather than LangGraph?* It is Microsoft's supported
  stack on Azure AI Foundry; the patterns (tools, workflows, fan-out) map either way.
- *How would you validate the shelf-life model?* Replace the heuristic with a
  model trained on lab stability data and compare predicted against measured days.
- *What stops a prompt injection reaching a tool?* Input guardrails, scoped
  tokens per skill, and approvals on consequential actions.
- *What would you cut for a first release?* APIM, Front Door and the event
  services; start with the service, one agent and the eval suite.
- *What is not done?* No deployment, `deploy.yml` is planned, live mode is not
  tested in CI.
