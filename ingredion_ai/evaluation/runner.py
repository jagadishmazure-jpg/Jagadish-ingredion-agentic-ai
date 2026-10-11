"""Offline eval runner: claim precision/recall + substitution top-1 (demo).

Run with ``python -m ingredion_ai.evaluation.runner``. All synthetic,
fully deterministic, no network.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ingredion_ai.agents.rd_formulation import analyzer, substitution
from ingredion_ai.agents.rd_formulation.regulatory import validate_claims
from ingredion_ai.data.loader import get_formula, get_ingredient
from ingredion_ai.evaluation.datasets import CLAIM_EVAL_SET, SUBSTITUTION_EVAL_SET
from ingredion_ai.evaluation.metrics import f1, precision, recall, top1_accuracy


@dataclass
class EvalResult:
    suite: str
    passed: bool
    total: int
    failures: int
    metrics: Dict[str, Any] = field(default_factory=dict)
    details: List[str] = field(default_factory=list)


def _reformulated_formula(formula_id: str) -> Dict[str, Any]:
    """Build the demo reformulation for *formula_id* (no adjustments)."""
    formula = get_formula(formula_id)
    analysis = analyzer.analyze_formula(formula)
    subs = substitution.suggest_substitutes(analysis["flagged"])
    return substitution.apply_substitutions(formula, subs)


def eval_claim_validation() -> EvalResult:
    """Precision/recall of the rule-based claim checker on the labeled set."""
    y_true: List[bool] = []
    y_pred: List[bool] = []
    details: List[str] = []
    for case in CLAIM_EVAL_SET:
        fid = case["formula_id"]
        base_id = fid.removesuffix("__clean_label")
        formula = _reformulated_formula(base_id) if fid != base_id else get_formula(fid)
        got = validate_claims(formula, [case["claim"]], region=case["region"])[0]["valid"]
        y_true.append(case["expected"])
        y_pred.append(got)
        if got != case["expected"]:
            details.append(
                f"MISMATCH {fid} claim={case['claim']!r}: "
                f"expected {case['expected']}, got {got}"
            )
    metrics = {
        "precision": precision(y_true, y_pred),
        "recall": recall(y_true, y_pred),
        "f1": f1(y_true, y_pred),
    }
    return EvalResult(
        suite="claim_validation",
        passed=not details,
        total=len(y_true),
        failures=len(details),
        metrics=metrics,
        details=details,
    )


def eval_substitution_relevance() -> EvalResult:
    """Top-1 accuracy of substitution recommendations on the labeled set."""
    expected: List[str] = []
    predicted: List[str] = []
    details: List[str] = []
    for case in SUBSTITUTION_EVAL_SET:
        old = get_ingredient(case["old_id"])
        candidates = substitution._candidates_for(old)
        top = candidates[0]["id"] if candidates else None
        expected.append(case["expected_top"])
        predicted.append(top)
        if top != case["expected_top"]:
            details.append(
                f"MISMATCH {case['old_id']}: expected {case['expected_top']}, got {top}"
            )
    return EvalResult(
        suite="substitution_relevance",
        passed=not details,
        total=len(expected),
        failures=len(details),
        metrics={"top1_accuracy": top1_accuracy(expected, predicted)},
        details=details,
    )


def run_all_evals() -> Dict[str, Any]:
    """Run every suite; return a pass/fail summary dict."""
    results = [eval_claim_validation(), eval_substitution_relevance()]
    total = sum(r.total for r in results)
    failures = sum(r.failures for r in results)
    return {
        "suites": [
            {
                "suite": r.suite,
                "passed": r.passed,
                "total": r.total,
                "failures": r.failures,
                "metrics": r.metrics,
                "details": r.details,
            }
            for r in results
        ],
        "total": total,
        "failures": failures,
        "passed": failures == 0,
        "demo": True,
    }


def main() -> int:
    summary = run_all_evals()
    for suite in summary["suites"]:
        status = "PASS" if suite["passed"] else "FAIL"
        print(f"[{status}] {suite['suite']}: "
              f"{suite['total'] - suite['failures']}/{suite['total']} "
              f"metrics={suite['metrics']}")
        for line in suite["details"]:
            print(f"    {line}")
    print(f"\nTotal: {summary['total'] - summary['failures']}/{summary['total']} "
          f"-> {'PASS' if summary['passed'] else 'FAIL'} (demo, synthetic data)")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
