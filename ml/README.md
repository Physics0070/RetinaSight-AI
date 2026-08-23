# ML — training, evaluation and export

This directory holds everything that *produces* a model. It is deliberately not
imported by the backend: the service depends only on `backend/app/ml/`, which
*consumes* the exported artefact.

```
ml/
├── datasets/       dataset adapters (APTOS, EyePACS, IDRiD, folder layout)
├── training/       training loop, transforms, model factory
├── evaluation/     metrics, confusion matrix, threshold reports
├── export/         ONNX / TorchScript export + parity check
├── models/         exported artefacts (git-ignored)
└── data/           datasets (git-ignored — never commit patient images)
```

---

## Getting a dataset

RetinaSight AI does not ship retinal data. The public DR datasets are all
license-gated and must be obtained by you, under their own terms:

| Dataset | Images | Grades | Access |
|---|---|---|---|
| **APTOS 2019** | 3,662 | 0–4 | Kaggle competition — accept rules, then `kaggle competitions download -c aptos2019-blindness-detection` |
| **EyePACS / Diabetic Retinopathy Detection** | 88,702 | 0–4 | Kaggle competition (~82 GB) |
| **Messidor-2** | 1,748 | 0–4 | ADCIS registration + signed agreement |
| **IDRiD** | 516 | 0–4 | IEEE DataPort |

All use the same five-class scale this project uses:

```
0 = No DR   1 = Mild   2 = Moderate   3 = Severe   4 = Proliferative
```

### Expected layout

Either a CSV manifest:

```
ml/data/aptos/
├── train.csv          id_code,diagnosis
└── train_images/      *.png
```

or a folder-per-class layout:

```
ml/data/<name>/
├── no_dr/  mild/  moderate/  severe/  proliferative/
```

Both are handled by `ml/datasets/retinal_dataset.py`.

---

## Training

```bash
cd ml
python -m training.train --data-dir data/aptos --epochs 20 --arch efficientnet_b0
```

Key flags:

| Flag | Default | Notes |
|---|---|---|
| `--arch` | `efficientnet_b0` | also `efficientnet_b3`, `mobilenet_v3_large`, `resnet18/50` |
| `--epochs` | `20` | |
| `--batch-size` | `16` | 6 GB VRAM comfortably fits B0 @224 |
| `--image-size` | `224` | must match the served input size |
| `--balance` | on | class-weighted loss — DR datasets are heavily imbalanced |
| `--amp` | on | mixed precision |

The loop uses the **same preprocessing as inference**
(`backend/app/ml/preprocessing.py`) so there is no train/serve skew — the retinal
crop, resize and ImageNet normalisation are shared code, not reimplemented.

## Evaluation

```bash
python -m evaluation.evaluate --checkpoint models/<run>/best.pt --data-dir data/aptos --split val
```

Reports accuracy, per-class precision/recall/F1, macro-F1, **quadratic weighted
kappa** (the standard DR metric) and a confusion matrix, and writes
`metrics.json`.

Those numbers — and only those numbers — are what you paste into
**Admin → Models → Validation**. The API rejects a "validated" status submitted
without them.

## Export

```bash
python -m export.to_onnx --checkpoint models/<run>/best.pt --output ../ml/models/dr-v2.onnx
```

Verifies logit parity between PyTorch and ONNX Runtime before writing.

---

## Clinical honesty

A model trained here is **not clinically validated**. Validation means
prospective evaluation on a representative population, by qualified people,
against a defined intended use. Held-out test accuracy is a development signal,
not evidence of clinical safety.

Register a trained model with `validation_status = not_validated` and leave it
there until real validation exists.
