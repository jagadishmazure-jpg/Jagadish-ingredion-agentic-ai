# Tool Calling: Patterns, Failure Modes, and When to Use Which

The `ingredion_ai/tools/` package is the project's tool-calling deep layer:
generation, composition, resilience, and sandboxing. Plain function-tools
(`ingredion_ai/framework/tools.py`) remain the default; reach for these when
the simple path isn't enough.

## Patterns

### 1. Plain function-tools (default)
Annotated Python functions the framework auto-converts. Use for: domain logic
you own, deterministic demo paths. Example: `analyze_ingredients`.

### 2. OpenAPI-generated tools (`tools/openapi.py`)
Parse an OpenAPI 3.x document → typed, schema-validated tools. Use for:
**legacy systems that already expose (or can expose) HTTP APIs** — no
hand-written client needed. The demo source is a synthetic LIMS
(`tools/lims_openapi.json`); production swaps the transport for real HTTP.

```python
tools = tools_from_openapi(load_lims_openapi(), real_http_transport)
sample = tools["getSample"](sampleId="SMP-1001")  # validated envelope
```

### 3. Chains (`tools/composition.py::chain`)
Sequential tools with output→input mapping (`"$step.field"` references or
callables). Use for: multi-step legacy procedures (fetch sample → fetch
tests → decide). The R&D agent's `lims_quality_lookup` is the live demo:
`getSample` → `getTestResults` composed into one tool.

### 4. Fan-out (`tools/composition.py::fan_out`)
Parallel independent calls, merged under tool names; failures captured, never
raised. Use for: independent lookups (CRM account + SAP inventory + LIMS
sample in one round-trip).

### 5. Fallback chains (`tools/resilience.py::FallbackChain`)
Ordered attempts; first success wins, attempts recorded. Use for: primary
system with a degraded secondary (live LIMS → cached snapshot).

### 6. Sandboxed execution (`tools/sandbox.py::run_sandboxed`)
Validate args → run with timeout → validate result → shaped error envelope.
Use for: every tool that touches a legacy system or untrusted input.

## Failure modes and mitigations

| Failure | Mitigation |
|---|---|
| Transient legacy outage | `call_with_retry` (bounded, backoff) |
| Persistent outage | `FallbackChain` → degraded source; envelope says which |
| Slow legacy call | Timeout in sandbox/bridge; `TIMEOUT` code, retryable |
| Bad arguments from the model | Input schema validation → `INVALID_ARGS` (no call made) |
| Malformed legacy response | Output schema validation → `INVALID_RESULT` |
| Partial batch failure | `partial_envelope` — use the successful subset |
| Legacy schema drift | Versioned catalog; deprecate, don't break |

## When to use which

- You own the logic → plain function-tool.
- Legacy has an API spec → OpenAPI-generated tool.
- Steps depend on each other → chain.
- Steps are independent → fan-out.
- Reliability matters → wrap with retry/fallback/sandbox.
- Agent-facing simplicity matters → expose the composed result as one tool
  (like `lims_quality_lookup`), keeping the machinery underneath.
