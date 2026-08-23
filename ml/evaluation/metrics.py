"""Classification metrics for DR screening.

Implemented directly on NumPy so evaluation has no scikit-learn dependency and
every number is traceable to its definition.

The headline metric for diabetic retinopathy is **quadratic weighted kappa**:
the grades are ordinal, so confusing "no DR" with "proliferative" is far worse
than confusing "mild" with "moderate". Plain accuracy treats those identically
and is therefore misleading on this task.
"""

from __future__ import annotations

import numpy as np

CLASS_NAMES: tuple[str, ...] = ("no_dr", "mild", "moderate", "severe", "proliferative")


def confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, num_classes: int) -> np.ndarray:
    matrix = np.zeros((num_classes, num_classes), dtype=np.int64)
    for true, pred in zip(y_true, y_pred):
        if 0 <= true < num_classes and 0 <= pred < num_classes:
            matrix[int(true), int(pred)] += 1
    return matrix


def per_class_metrics(matrix: np.ndarray) -> list[dict]:
    results = []
    for index in range(matrix.shape[0]):
        true_positive = int(matrix[index, index])
        false_positive = int(matrix[:, index].sum() - true_positive)
        false_negative = int(matrix[index, :].sum() - true_positive)
        support = int(matrix[index, :].sum())

        precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else 0.0
        recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        results.append(
            {
                "class": CLASS_NAMES[index] if index < len(CLASS_NAMES) else str(index),
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "support": support,
            }
        )
    return results


def quadratic_weighted_kappa(
    y_true: np.ndarray, y_pred: np.ndarray, num_classes: int
) -> float:
    """Cohen's kappa with quadratic weights — the standard DR grading metric.

    1.0 = perfect agreement, 0.0 = chance, negative = worse than chance.
    """
    if y_true.size == 0:
        return 0.0

    observed = confusion_matrix(y_true, y_pred, num_classes).astype(np.float64)

    weights = np.zeros((num_classes, num_classes), dtype=np.float64)
    for i in range(num_classes):
        for j in range(num_classes):
            weights[i, j] = ((i - j) ** 2) / ((num_classes - 1) ** 2)

    true_hist = np.bincount(y_true.astype(int), minlength=num_classes).astype(np.float64)
    pred_hist = np.bincount(y_pred.astype(int), minlength=num_classes).astype(np.float64)
    expected = np.outer(true_hist, pred_hist)

    # Scale expected to the same total as observed.
    observed_sum = observed.sum()
    expected_sum = expected.sum()
    if observed_sum == 0 or expected_sum == 0:
        return 0.0
    expected = expected * (observed_sum / expected_sum)

    denominator = float((weights * expected).sum())
    if denominator == 0:
        return 0.0
    return float(1.0 - (weights * observed).sum() / denominator)


def referable_dr_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Binary view: is this case referable (moderate or worse)?

    This is the decision the product actually makes, so it is reported
    alongside the five-class metrics. Sensitivity matters more than
    specificity here — a missed severe case is far costlier than an
    unnecessary referral.
    """
    if y_true.size == 0:
        return {"sensitivity": 0.0, "specificity": 0.0, "precision": 0.0}

    true_referable = y_true >= 2
    pred_referable = y_pred >= 2

    true_positive = int((true_referable & pred_referable).sum())
    false_negative = int((true_referable & ~pred_referable).sum())
    false_positive = int((~true_referable & pred_referable).sum())
    true_negative = int((~true_referable & ~pred_referable).sum())

    def ratio(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    return {
        "sensitivity": ratio(true_positive, true_positive + false_negative),
        "specificity": ratio(true_negative, true_negative + false_positive),
        "precision": ratio(true_positive, true_positive + false_positive),
        "true_positive": true_positive,
        "false_negative": false_negative,
        "false_positive": false_positive,
        "true_negative": true_negative,
    }


def evaluate_predictions(
    y_true: np.ndarray, y_pred: np.ndarray, num_classes: int = len(CLASS_NAMES)
) -> dict:
    """Full metric set for one set of predictions."""
    if y_true.size == 0:
        return {
            "accuracy": 0.0,
            "macro_f1": 0.0,
            "quadratic_kappa": 0.0,
            "per_class": [],
            "confusion_matrix": [],
            "referable_dr": {},
            "samples": 0,
        }

    matrix = confusion_matrix(y_true, y_pred, num_classes)
    per_class = per_class_metrics(matrix)

    accuracy = float((y_true == y_pred).mean())
    scored = [c["f1"] for c in per_class if c["support"] > 0]
    macro_f1 = float(np.mean(scored)) if scored else 0.0

    return {
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "quadratic_kappa": round(quadratic_weighted_kappa(y_true, y_pred, num_classes), 4),
        "per_class": per_class,
        "confusion_matrix": matrix.tolist(),
        "referable_dr": referable_dr_metrics(y_true, y_pred),
        "samples": int(y_true.size),
    }


def format_report(metrics: dict) -> str:
    """Human-readable summary for the console."""
    lines = [
        "",
        f"Samples:            {metrics['samples']}",
        f"Accuracy:           {metrics['accuracy']:.4f}",
        f"Macro F1:           {metrics['macro_f1']:.4f}",
        f"Quadratic kappa:    {metrics['quadratic_kappa']:.4f}",
        "",
        f"{'class':<16}{'precision':>10}{'recall':>10}{'f1':>10}{'support':>10}",
        "-" * 56,
    ]
    for entry in metrics["per_class"]:
        lines.append(
            f"{entry['class']:<16}{entry['precision']:>10.4f}"
            f"{entry['recall']:>10.4f}{entry['f1']:>10.4f}{entry['support']:>10}"
        )

    referable = metrics.get("referable_dr") or {}
    if referable:
        lines += [
            "",
            "Referable DR (moderate or worse):",
            f"  sensitivity {referable.get('sensitivity', 0):.4f}   "
            f"specificity {referable.get('specificity', 0):.4f}",
        ]

    lines += ["", "Confusion matrix (rows = true, columns = predicted):"]
    header = " " * 16 + "".join(f"{name[:8]:>10}" for name in CLASS_NAMES)
    lines.append(header)
    for index, row in enumerate(metrics["confusion_matrix"]):
        name = CLASS_NAMES[index] if index < len(CLASS_NAMES) else str(index)
        lines.append(f"{name:<16}" + "".join(f"{value:>10}" for value in row))

    return "\n".join(lines)
