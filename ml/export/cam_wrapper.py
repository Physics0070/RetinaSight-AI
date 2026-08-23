"""Wrap a classifier so the exported graph also emits class-activation maps.

Why this exists
---------------
ONNX Runtime has no gradients, so true Grad-CAM cannot be computed at serving
time from a plain exported classifier — the served model would return a blank
heatmap and the explainability feature would be hollow.

For every architecture used here the final stages are
``features -> global average pool -> linear``. Under that structure the
gradient of class *c* with respect to the pooled features is exactly the
classifier weight row ``W[c]``, so Grad-CAM reduces to

    CAM_c(x, y) = sum_k  W[c, k] * A_k(x, y)

which is a plain tensor contraction. Baking it into the graph gives the serving
runtime the same map PyTorch would produce, with no gradients required.

The wrapper returns ``(logits, cam, grade)`` where cam has shape
``(batch, num_classes, H, W)``; the provider selects the reported grade's map.

Why the graph also emits the decided grade
------------------------------------------
The five logits do not by themselves say which grade the model reports. Models
trained with the ordinal objective decide by *rounding the expected grade*
rather than by argmax (see ``training/losses.py``), and the two rules disagree
on a meaningful fraction of cases — a distribution split between grades 2 and 4
has argmax 2 but expectation 3.

If the graph emitted only logits, the serving runtime would have to know which
rule the checkpoint was trained under, and getting that wrong would silently
serve a model that cannot reproduce its own reported metrics. Baking the
decision into the graph makes the artefact self-describing: every consumer —
cloud, edge, test — reads the same grade the evaluation harness measured.
"""

from __future__ import annotations

import torch
import torch.nn as nn


def _final_linear(model: nn.Module) -> nn.Linear:
    """The classifier layer whose weights define the CAM."""
    if hasattr(model, "classifier"):
        classifier = model.classifier
        if isinstance(classifier, nn.Linear):
            return classifier
        if isinstance(classifier, nn.Sequential):
            for layer in reversed(classifier):
                if isinstance(layer, nn.Linear):
                    return layer
    if hasattr(model, "fc") and isinstance(model.fc, nn.Linear):
        return model.fc
    raise ValueError("Could not locate the final linear layer for CAM extraction.")


#: Decision rules a checkpoint may have been trained and evaluated under.
EXPECTED_GRADE = "expected_grade"
ARGMAX = "argmax"


class CamWrapper(nn.Module):
    """Emits logits, per-class activation maps, and the decided grade.

    Args:
        decision_rule: how the model turns logits into a reported grade.
            ``expected_grade`` rounds the softmax-weighted mean grade (what the
            ordinal objective optimises); ``argmax`` takes the most likely
            class. This must match the rule the checkpoint was evaluated under.
    """

    def __init__(
        self,
        model: nn.Module,
        arch: str,
        *,
        decision_rule: str = ARGMAX,
        image_size: int = 224,
    ) -> None:
        super().__init__()
        if decision_rule not in (EXPECTED_GRADE, ARGMAX):
            raise ValueError(
                f"Unknown decision rule {decision_rule!r}; "
                f"expected {EXPECTED_GRADE!r} or {ARGMAX!r}."
            )
        self.model = model
        self.arch = arch
        self.decision_rule = decision_rule
        self.is_resnet = arch.startswith("resnet")
        self._linear = _final_linear(model)

        # Grade values 0..K-1, for the expectation over the softmax. Registered
        # as a buffer so the constant is captured in the exported graph.
        self.register_buffer(
            "grades",
            torch.arange(self._linear.out_features, dtype=torch.float32),
            persistent=False,
        )

        # Probe the feature width once so the CAM path can be chosen up front.
        # Probed at the model's own input size: spatial dims do not change the
        # channel count, but a size the backbone rejects would fail here.
        model.eval()
        with torch.no_grad():
            self._feature_channels = int(
                self._features(torch.zeros(1, 3, image_size, image_size)).shape[1]
            )

    def _features(self, x: torch.Tensor) -> torch.Tensor:
        if self.is_resnet:
            m = self.model
            x = m.maxpool(m.relu(m.bn1(m.conv1(x))))
            x = m.layer1(x)
            x = m.layer2(x)
            x = m.layer3(x)
            return m.layer4(x)
        return self.model.features(x)

    def _classify(self, features: torch.Tensor) -> torch.Tensor:
        pooled = torch.flatten(
            nn.functional.adaptive_avg_pool2d(features, (1, 1)), 1
        )
        if self.is_resnet:
            return self.model.fc(pooled)
        classifier = self.model.classifier
        return classifier(pooled) if not isinstance(classifier, nn.Linear) else classifier(pooled)

    @property
    def supports_exact_cam(self) -> bool:
        """True when features feed the final linear directly.

        Some heads (MobileNet-V3) insert another linear plus a non-linearity
        between the pooled features and the classifier. The CAM identity does
        not hold through that, so an exact per-class map is unavailable and the
        wrapper falls back to a channel-mean saliency map instead of silently
        producing a wrong attribution.
        """
        return self._feature_channels == self._linear.in_features

    def decide(self, logits: torch.Tensor) -> torch.Tensor:
        """The grade the model reports, under its own decision rule."""
        if self.decision_rule == ARGMAX:
            return logits.argmax(dim=1)

        # Rounding the expected grade. torch.round and the ONNX Round operator
        # both round half to even, so the exported graph and the evaluation
        # harness agree exactly on ties.
        probabilities = nn.functional.softmax(logits, dim=1)
        expected = (probabilities * self.grades).sum(dim=1)
        return expected.round().clamp(0, self.grades.numel() - 1).to(torch.int64)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        features = self._features(x)
        logits = self._classify(features)

        if self.supports_exact_cam:
            # CAM_c(x,y) = sum_k W[c,k] * A_k(x,y) — a 1x1 convolution in effect.
            weight = self._linear.weight  # (num_classes, channels)
            cam = torch.einsum("bkhw,ck->bchw", features, weight)
        else:
            # Class-agnostic fallback: mean activation, broadcast per class.
            mean_activation = features.mean(dim=1, keepdim=True)
            cam = mean_activation.expand(-1, logits.shape[1], -1, -1)

        return logits, cam, self.decide(logits)


def verify_wrapper_matches(model: nn.Module, wrapper: CamWrapper, sample: torch.Tensor) -> float:
    """The wrapper must not change the model's predictions.

    Returns the max logit difference between the original model and the
    wrapper's reconstructed forward pass.
    """
    model.eval()
    wrapper.eval()
    with torch.no_grad():
        original = model(sample)
        wrapped = wrapper(sample)[0]
    return float((original - wrapped).abs().max())
