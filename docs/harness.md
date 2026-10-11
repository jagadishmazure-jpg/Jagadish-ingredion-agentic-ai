# Harness Engineering

> Demo project. All data synthetic and fictional. Not affiliated with Ingredion.

The model is only half the system. The **harness** is everything around it:
retries, timeouts, failure isolation, guardrails, and the observability hooks
that make runs measurable. `ingredion_ai.harness` wraps agent `execute()` calls
(or any callable) with that machinery.

```python
from ingredion_ai.harness import Harness, policy_guardrail

harness = Harness(max_retries=2, base_delay=0.2, timeout_seconds=10.0)
harness.pre_hooks.append(policy_guardrail("analyze_ingredients", agent="rd_formulation"))
harness.on_run_end.append(lambda record: print(record))

result = harness.run(agent.execute, "analyze_ingredients", {"formula": "demo-1"})
```

## Retries and backoff

`Harness.run(fn, *args, **kwargs)` tries the callable up to
`max_retries + 1` times. Between attempts it sleeps
`base_delay * 2**(n-1)` — **deterministic exponential backoff, no jitter** —
so a flaky dependency gets breathing room and demo runs stay reproducible.
The last attempt's error is re-raised once retries are exhausted, preserving
the original exception type.

## Timeouts

Each attempt runs in a single-worker `concurrent.futures.ThreadPoolExecutor`
with `future.result(timeout=timeout_seconds)`. If the attempt overruns,
`TimeoutError` is raised and treated like any other failure (retried, then
surfaced). Timeouts bound the worst case: one stuck tool call can no longer
hang the whole agent loop.

## Circuit breaker

`CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)` isolates a
persistently failing dependency so retries don't become a self-inflicted DDoS:

- **closed** — calls flow; a success resets the failure count.
- **open** — after `failure_threshold` consecutive failures, calls are
  rejected immediately with `CircuitOpenError`.
- **half-open** — once the cooldown expires, one trial call is allowed; if it
  succeeds the circuit closes, if it fails the circuit re-opens and the
  cooldown restarts.

```python
from ingredion_ai.harness import CircuitBreaker

breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
result = breaker.call(flaky_tool, payload)   # raises CircuitOpenError when open
```

## Guardrails

- **Pre-hooks** (`harness.pre_hooks`) run as `hook(fn_name, *args, **kwargs)`
  *before* execution. A hook returning `False` **vetoes** the run and raises
  `GuardrailViolation` — nothing executes.
- **Post-hooks** (`harness.post_hooks`) run as `hook(fn_name, result)` after
  a successful attempt. They only observe; they cannot veto.
- **`policy_guardrail(action_name, agent=...)`** builds a pre-hook from
  `ingredion_ai.governance.policy`: it calls `check_action(agent,
  action_name)` and vetoes anything the policy doesn't allow-list. The denial
  reason is kept on the hook as `last_reason`. This is how demo policy ("agents
  never place orders, modify SAP, or publish claims") is enforced at the
  execution layer rather than trusted to the prompt.

## Eval hooks

`harness.on_run_end` callbacks receive a `RunRecord` dict after every terminal
run — success, failure, **or** veto (vetoes report `attempts: 0`):

```python
{"fn_name": "analyze_ingredients", "success": True,
 "attempts": 2, "latency_s": 0.34, "error": None}
```

`attempts` counts total tries (first attempt + retries), `latency_s` is total
wall-clock time, and `error` is `None` on success or `"Type: message"` on
failure. These records are the raw material for eval dashboards: retry rate,
p99 latency, and guardrail veto rate per agent.

## How it wraps agent `execute()` calls

The harness is call-agnostic — it wraps `agent.execute(task_name, payload)`
exactly like any function. The recommended layering for the demo agents is:

```text
on_run_end (eval record)
   └─ post_hooks (observe result)
       └─ retries + timeout + backoff
           └─ pre_hooks (guardrails: policy veto)
               └─ agent.execute(task_name, payload)
```

Policy is checked *before* execution; observability is emitted *after*.
