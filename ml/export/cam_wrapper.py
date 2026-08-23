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

The wrapper returns ``(logits, cam)`` where cam has shape
``(batch, num_classes, H, W)``; the provider selects the predicted class's map.
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


class CamWrapper(nn.Module):
    """Emits logits plus per-class activation maps."""

    def __init__(self, model: nn.Module, arch: str) -> None:
        super().__init__()
        self.model = model
        self.arch = arch
        self.is_resnet = arch.startswith("resnet")
        self._linear = _final_linear(model)

        # Probe the feature width once so the CAM path can be chosen up front.
        model.eval()
        with torch.no_grad():
            self._feature_channels = int(
                self._features(torch.zeros(1, 3, 224, 224)).shape[1]
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

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
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

        return logits, cam


def verify_wrapper_matches(model: nn.Module, wrapper: CamWrapper, sample: torch.Tensor) -> float:
    """The wrapper must not change the model's predictions.

    Returns the max logit difference between the original model and the
    wrapper's reconstructed forward pass.
    """
    model.eval()
    wrapper.eval()
    with torch.no_grad():
        original = model(sample)
        wrapped, _ = wrapper(sample)
    return float((original - wrapped).abs().max())
