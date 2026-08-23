"""Model factory.

Exposes the architectures named in the product proposal — EfficientNet,
MobileNet and ResNet — behind one call, so the architecture is a configuration
choice rather than a code change.

Backbones start from ImageNet weights: retinal datasets are small relative to
the capacity of these networks, and transfer learning is what makes training on
a few thousand fundus images viable at all.
"""

from __future__ import annotations

import torch.nn as nn

# architecture -> (torchvision factory, weights enum name)
SUPPORTED = {
    "efficientnet_b0": ("efficientnet_b0", "EfficientNet_B0_Weights"),
    "efficientnet_b3": ("efficientnet_b3", "EfficientNet_B3_Weights"),
    "mobilenet_v3_large": ("mobilenet_v3_large", "MobileNet_V3_Large_Weights"),
    "mobilenet_v2": ("mobilenet_v2", "MobileNet_V2_Weights"),
    "resnet18": ("resnet18", "ResNet18_Weights"),
    "resnet50": ("resnet50", "ResNet50_Weights"),
}


def build_model(arch: str, *, num_classes: int, pretrained: bool = True) -> nn.Module:
    """Build a backbone with its classifier resized to the DR grading scale."""
    import torchvision

    if arch not in SUPPORTED:
        raise ValueError(
            f"Unsupported architecture '{arch}'. Choose one of: {', '.join(SUPPORTED)}"
        )

    factory_name, weights_name = SUPPORTED[arch]
    weights = None
    if pretrained:
        try:
            weights = getattr(torchvision.models, weights_name).DEFAULT
        except AttributeError:
            weights = None

    model = getattr(torchvision.models, factory_name)(weights=weights)
    replace_classifier(model, num_classes)
    return model


def replace_classifier(model: nn.Module, num_classes: int) -> None:
    """Resize the final linear layer in place.

    Mirrors backend/app/ml/providers/torch_provider.py, so a checkpoint trained
    here loads there without shape surprises.
    """
    if hasattr(model, "classifier"):
        classifier = model.classifier
        if isinstance(classifier, nn.Sequential):
            for index in range(len(classifier) - 1, -1, -1):
                if isinstance(classifier[index], nn.Linear):
                    classifier[index] = nn.Linear(classifier[index].in_features, num_classes)
                    return
        elif isinstance(classifier, nn.Linear):
            model.classifier = nn.Linear(classifier.in_features, num_classes)
            return

    if hasattr(model, "fc") and isinstance(model.fc, nn.Linear):
        model.fc = nn.Linear(model.fc.in_features, num_classes)
        return

    raise ValueError("Could not locate a classifier layer to resize.")
