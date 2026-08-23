"""Metric correctness.

These matter because the numbers they produce are the only figures allowed into
the model registry. A wrong metric here would launder a bad model into looking
acceptable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.metrics import (  # noqa: E402
    CLASS_NAMES,
    confusion_matrix,
    evaluate_predictions,
    per_class_metrics,
    quadratic_weighted_kappa,
    referable_dr_metrics,
)


def test_perfect_prediction_scores_one() -> None:
    y = np.array([0, 1, 2, 3, 4, 0, 2, 4])

    metrics = evaluate_predictions(y, y.copy())

    assert metrics["accuracy"] == 1.0
    assert metrics["macro_f1"] == 1.0
    assert metrics["quadratic_kappa"] == 1.0


def test_confusion_matrix_counts_correctly() -> None:
    y_true = np.array([0, 0, 1, 2])
    y_pred = np.array([0, 1, 1, 2])

    matrix = confusion_matrix(y_true, y_pred, 5)

    assert matrix[0, 0] == 1  # one correct no_dr
    assert matrix[0, 1] == 1  # one no_dr predicted as mild
    assert matrix[1, 1] == 1
    assert matrix[2, 2] == 1
    assert matrix.sum() == 4


def test_kappa_punishes_distant_errors_more_than_near_ones() -> None:
    """The grades are ordinal — confusing no_dr with proliferative is far worse
    than confusing mild with moderate, and the metric must reflect that.

    Note the true labels must span several classes: with a single true class,
    expected agreement equals observed and kappa is degenerate (0) regardless
    of how wrong the prediction is.
    """
    y_true = np.array([0, 1, 2, 3, 4])

    near_miss = quadratic_weighted_kappa(y_true, np.array([0, 1, 2, 3, 3]), 5)
    far_miss = quadratic_weighted_kappa(y_true, np.array([0, 1, 2, 3, 0]), 5)

    assert far_miss < near_miss


def test_kappa_is_degenerate_for_a_single_true_class() -> None:
    """Documents a real limitation: kappa needs variation in the true labels.

    A validation split containing only one grade produces kappa 0 no matter what
    the model predicts — which is why the split is stratified.
    """
    y_true = np.zeros(4, dtype=int)

    assert quadratic_weighted_kappa(y_true, np.array([0, 0, 0, 1]), 5) == 0.0
    assert quadratic_weighted_kappa(y_true, np.array([0, 0, 0, 4]), 5) == 0.0


def test_accuracy_alone_would_hide_a_useless_model() -> None:
    """A model that always predicts 'no DR' scores well on accuracy against a
    realistically skewed dataset. Macro-F1 must expose it."""
    # 90% grade 0, 10% referable — roughly the real-world skew.
    y_true = np.array([0] * 90 + [2] * 5 + [3] * 3 + [4] * 2)
    y_pred = np.zeros_like(y_true)  # predicts "no DR" for everything

    metrics = evaluate_predictions(y_true, y_pred)

    assert metrics["accuracy"] == pytest.approx(0.90, abs=0.01)
    assert metrics["macro_f1"] < 0.30, "macro-F1 must expose the collapsed model"
    assert metrics["referable_dr"]["sensitivity"] == 0.0


def test_macro_f1_ignores_classes_with_no_support() -> None:
    """Averaging in absent classes as zero would understate a model unfairly."""
    y_true = np.array([0, 0, 1, 1])
    y_pred = np.array([0, 0, 1, 1])

    metrics = evaluate_predictions(y_true, y_pred)

    assert metrics["macro_f1"] == 1.0


def test_per_class_metrics_are_computed_independently() -> None:
    y_true = np.array([0, 0, 1, 1, 2, 2])
    y_pred = np.array([0, 1, 1, 1, 2, 0])

    results = per_class_metrics(confusion_matrix(y_true, y_pred, 5))
    by_class = {entry["class"]: entry for entry in results}

    assert by_class["no_dr"]["support"] == 2
    assert by_class["no_dr"]["recall"] == pytest.approx(0.5)
    assert by_class["mild"]["recall"] == pytest.approx(1.0)
    # Metrics are rounded to 4 decimal places for stable JSON output.
    assert by_class["mild"]["precision"] == pytest.approx(2 / 3, abs=1e-4)


def test_referable_dr_is_the_decision_the_product_makes() -> None:
    """Moderate or worse is referable; the binary view is what drives triage."""
    y_true = np.array([0, 1, 2, 3, 4])
    y_pred = np.array([0, 1, 2, 3, 4])

    referable = referable_dr_metrics(y_true, y_pred)

    assert referable["sensitivity"] == 1.0
    assert referable["specificity"] == 1.0
    assert referable["true_positive"] == 3  # grades 2, 3, 4
    assert referable["true_negative"] == 2  # grades 0, 1


def test_missed_severe_case_shows_as_lost_sensitivity() -> None:
    """The costliest failure mode must be visible in the metrics."""
    y_true = np.array([0, 0, 4, 4])
    y_pred = np.array([0, 0, 0, 0])  # both severe cases missed

    referable = referable_dr_metrics(y_true, y_pred)

    assert referable["sensitivity"] == 0.0
    assert referable["false_negative"] == 2


def test_empty_input_returns_zeros_rather_than_crashing() -> None:
    metrics = evaluate_predictions(np.array([]), np.array([]))

    assert metrics["samples"] == 0
    assert metrics["accuracy"] == 0.0
    assert metrics["quadratic_kappa"] == 0.0


def test_report_covers_the_full_grading_scale() -> None:
    y_true = np.arange(5)
    metrics = evaluate_predictions(y_true, y_true.copy())

    assert len(metrics["per_class"]) == len(CLASS_NAMES)
    assert [entry["class"] for entry in metrics["per_class"]] == list(CLASS_NAMES)


def test_metrics_are_json_serialisable() -> None:
    """They are written to metrics.json and read by the registry."""
    import json

    metrics = evaluate_predictions(np.array([0, 1, 2]), np.array([0, 1, 1]))

    restored = json.loads(json.dumps(metrics))
    assert restored["samples"] == 3
