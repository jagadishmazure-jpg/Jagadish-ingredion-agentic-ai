"""Eval metrics: precision/recall/F1 and top-1 accuracy (demo)."""

from __future__ import annotations

from typing import List


def precision(y_true: List[bool], y_pred: List[bool]) -> float:
    """Precision over boolean labels (0.0 when no positive predictions)."""
    tp = sum(1 for t, p in zip(y_true, y_pred) if t and p)
    fp = sum(1 for t, p in zip(y_true, y_pred) if not t and p)
    if tp + fp == 0:
        return 0.0
    return round(tp / (tp + fp), 4)


def recall(y_true: List[bool], y_pred: List[bool]) -> float:
    """Recall over boolean labels (0.0 when no positive labels)."""
    tp = sum(1 for t, p in zip(y_true, y_pred) if t and p)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t and not p)
    if tp + fn == 0:
        return 0.0
    return round(tp / (tp + fn), 4)


def f1(y_true: List[bool], y_pred: List[bool]) -> float:
    """Harmonic mean of precision and recall."""
    p, r = precision(y_true, y_pred), recall(y_true, y_pred)
    if p + r == 0:
        return 0.0
    return round(2 * p * r / (p + r), 4)


def top1_accuracy(expected: List[str], predicted: List[str]) -> float:
    """Fraction of cases where the top prediction matches the label."""
    if not expected:
        return 0.0
    hits = sum(1 for e, p in zip(expected, predicted) if e == p)
    return round(hits / len(expected), 4)
