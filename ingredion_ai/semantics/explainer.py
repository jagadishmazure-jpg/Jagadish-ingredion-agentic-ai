"""Deterministic "why did it change" attribution for governed metrics.

Given a metric and base-measure values for two periods, decompose the
metric's delta into per-driver contributions using sequential
(one-at-a-time) variance decomposition over the metric's formula inputs:

1. Start from period-A inputs.
2. Flip each input to its period-B value, in the metric's declared input
   order, attributing the marginal change to that driver.
3. The contributions telescope: they sum *exactly* to the total delta.

Sequential attribution is order-dependent — the input order declared on
the metric definition is the documented attribution order, and the
confidence note says so. Deterministic, no LLM, no network.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ingredion_ai.semantics.metrics import MetricDefinition

_ZERO_TOL = 1e-9


def explain_change(
    metric: MetricDefinition,
    period_a: Dict[str, float],
    period_b: Dict[str, float],
    label_a: str = "period A",
    label_b: str = "period B",
) -> Dict[str, Any]:
    """Decompose the metric delta between two periods into drivers.

    Returns ``value_a``, ``value_b``, ``delta``, a ``drivers`` list with
    per-input contributions (only non-zero contributions are listed), a
    ``residual`` (should be ~0), and a ``confidence_note``.
    """
    value_a = metric.evaluate(period_a)
    value_b = metric.evaluate(period_b)
    delta = value_b - value_a

    drivers: List[Dict[str, Any]] = []
    current = {k: float(v) for k, v in period_a.items()}
    for name in metric.inputs:
        before = metric.evaluate(current)
        current[name] = float(period_b[name])
        contribution = metric.evaluate(current) - before
        if abs(contribution) > _ZERO_TOL:
            drivers.append(
                {
                    "driver": name,
                    "from": float(period_a[name]),
                    "to": float(period_b[name]),
                    "contribution": round(contribution, 6),
                    "direction": "up" if contribution > 0 else "down",
                    "cites": f"{metric.name}@{metric.version} :: input {name!r}",
                }
            )

    explained = sum(d["contribution"] for d in drivers)
    residual = delta - explained
    if abs(delta) <= _ZERO_TOL:
        note = (
            "No change between periods: all driver contributions are zero. "
            "Nothing moved."
        )
    else:
        note = (
            "Sequential attribution in the metric's declared input order "
            f"({', '.join(metric.inputs)}); contributions are order-dependent "
            "estimates. Residual "
            f"{residual:.2e} confirms the decomposition accounts for the delta."
        )
    return {
        "metric": metric.name,
        "metric_version": metric.version,
        "unit": metric.unit,
        "formula": metric.formula,
        "label_a": label_a,
        "label_b": label_b,
        "value_a": round(value_a, 6),
        "value_b": round(value_b, 6),
        "delta": round(delta, 6),
        "drivers": drivers,
        "residual": residual,
        "confidence_note": note,
    }


def summarize(attribution: Dict[str, Any]) -> str:
    """One-paragraph, cited plain-language summary of an attribution."""
    unit = attribution["unit"]
    lines = [
        f"{attribution['metric']} moved from {attribution['value_a']} to "
        f"{attribution['value_b']} {unit} ({attribution['label_a']} → "
        f"{attribution['label_b']}), a delta of {attribution['delta']}."
    ]
    for d in attribution["drivers"]:
        lines.append(
            f"- {d['driver']}: {d['from']} → {d['to']} contributed "
            f"{d['contribution']} ({d['direction']}) [{d['cites']}]"
        )
    if not attribution["drivers"]:
        lines.append("- No driver moved; the metric is flat.")
    return "\n".join(lines)
