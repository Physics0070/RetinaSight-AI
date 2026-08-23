"""Loss functions that respect the ordinal nature of DR grading.

The problem with plain cross-entropy
------------------------------------
The five DR grades are *ordered*. Cross-entropy treats them as unordered
categories, so predicting "no DR" for a proliferative case costs exactly the
same as predicting "mild" for a moderate one. Clinically those are wildly
different errors, and quadratic weighted kappa — the metric this task is judged
on — penalises by squared distance.

Optimising cross-entropy while being measured on kappa is a structural mismatch.

The fix, without changing the model's shape
-------------------------------------------
A true ordinal head (regression + thresholds, or K-1 binary outputs) would change
the output tensor, which would break the exported ONNX contract and every
provider that consumes five logits.

Instead this keeps the five-logit output and adds a term that penalises
*distance*: the softmax-weighted expected grade is pushed toward the true grade
with a squared error. That is differentiable, needs no architectural change, and
directly targets what kappa measures.

    loss = CE(logits, y) + lambda * (E[grade] - y)^2

where E[grade] = sum_k  k * softmax(logits)_k
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class OrdinalAwareLoss(nn.Module):
    """Cross-entropy plus a squared-distance penalty on the expected grade.

    Args:
        class_weights: per-class weights for the cross-entropy term. DR datasets
            are heavily skewed, so this is normally required.
        distance_weight: strength of the ordinal term. 0 reduces this to plain
            weighted cross-entropy.
        label_smoothing: applied to the cross-entropy term only.
    """

    def __init__(
        self,
        *,
        class_weights: torch.Tensor | None = None,
        distance_weight: float = 0.5,
        label_smoothing: float = 0.05,
        num_classes: int = 5,
    ) -> None:
        super().__init__()
        self.distance_weight = float(distance_weight)
        self.cross_entropy = nn.CrossEntropyLoss(
            weight=class_weights, label_smoothing=label_smoothing
        )
        # Grade values 0..K-1, used to take the expectation over the softmax.
        self.register_buffer(
            "grades", torch.arange(num_classes, dtype=torch.float32), persistent=False
        )

    def expected_grade(self, logits: torch.Tensor) -> torch.Tensor:
        """Softmax-weighted mean grade — a continuous severity estimate."""
        return (F.softmax(logits, dim=1) * self.grades.to(logits.device)).sum(dim=1)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        loss = self.cross_entropy(logits, targets)

        if self.distance_weight > 0:
            expected = self.expected_grade(logits)
            # Squared distance mirrors the quadratic weighting in kappa.
            distance = F.mse_loss(expected, targets.float())
            loss = loss + self.distance_weight * distance

        return loss


def expected_grade_predictions(logits: torch.Tensor, num_classes: int = 5) -> torch.Tensor:
    """Predict by rounding the expected grade rather than taking the argmax.

    On an ordinal task this is often the better decision rule: a distribution
    split between grades 2 and 4 has argmax 2 (or 4), but its expectation is 3 —
    which is usually the safer call clinically and scores better under kappa.
    """
    grades = torch.arange(num_classes, dtype=torch.float32, device=logits.device)
    expected = (F.softmax(logits, dim=1) * grades).sum(dim=1)
    return expected.round().clamp(0, num_classes - 1).long()
