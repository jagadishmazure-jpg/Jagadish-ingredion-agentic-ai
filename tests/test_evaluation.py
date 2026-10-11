"""Tests for the evaluation package: metrics, datasets, runner."""

from ingredion_ai.evaluation import datasets, metrics, runner


# -- metrics -------------------------------------------------------------------


def test_precision_recall_f1_perfect():
    y_true = [True, True, False, False]
    y_pred = [True, True, False, False]
    assert metrics.precision(y_true, y_pred) == 1.0
    assert metrics.recall(y_true, y_pred) == 1.0
    assert metrics.f1(y_true, y_pred) == 1.0


def test_precision_partial():
    # 1 true positive, 1 false positive -> precision 0.5
    assert metrics.precision([True, False], [True, True]) == 0.5


def test_recall_partial():
    # 1 true positive, 1 false negative -> recall 0.5
    assert metrics.recall([True, True], [True, False]) == 0.5


def test_metrics_empty_predictions_safe():
    assert metrics.precision([True], [False]) == 0.0
    assert metrics.recall([False], [False]) == 0.0
    assert metrics.f1([False], [False]) == 0.0


def test_top1_accuracy():
    assert metrics.top1_accuracy(["a", "b", "c"], ["a", "x", "c"]) == round(2 / 3, 4)
    assert metrics.top1_accuracy([], []) == 0.0


# -- datasets --------------------------------------------------------------------


def test_claim_eval_set_shape():
    assert len(datasets.CLAIM_EVAL_SET) == 10
    for case in datasets.CLAIM_EVAL_SET:
        assert {"formula_id", "claim", "region", "expected"} <= set(case)
        assert isinstance(case["expected"], bool)


def test_substitution_eval_set_shape():
    assert len(datasets.SUBSTITUTION_EVAL_SET) == 10
    for case in datasets.SUBSTITUTION_EVAL_SET:
        assert {"old_id", "expected_top"} <= set(case)


def test_claim_eval_set_covers_new_scenarios():
    formula_ids = {c["formula_id"] for c in datasets.CLAIM_EVAL_SET}
    # beverage + bakery scenario coverage beyond the original cake
    assert len(formula_ids) >= 2


# -- runner ----------------------------------------------------------------------


def test_eval_claim_validation_passes():
    result = runner.eval_claim_validation()
    assert result.passed
    assert result.failures == 0
    assert result.metrics["precision"] == 1.0
    assert result.metrics["recall"] == 1.0


def test_eval_substitution_relevance_passes():
    result = runner.eval_substitution_relevance()
    assert result.passed
    assert result.metrics["top1_accuracy"] == 1.0


def test_run_all_evals_summary():
    summary = runner.run_all_evals()
    assert summary["passed"]
    assert summary["failures"] == 0
    assert summary["total"] == 20
    assert len(summary["suites"]) == 2


def test_eval_main_returns_zero(capsys):
    assert runner.main() == 0
    out = capsys.readouterr().out
    assert "PASS" in out
    assert "20/20" in out
