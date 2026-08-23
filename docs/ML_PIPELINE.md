# ML pipeline

```
raw bytes → decode → crop to retinal disc → resize → normalise
          → QUALITY GATE ─(reject)→ retake with guidance
          → model inference → 5-class DR probabilities
          → Grad-CAM explanation
          → risk engine → referral engine
```

> **The model shipped in this repository is a labelled placeholder.** It has not
> been trained or validated on retinal data. No accuracy, sensitivity,
> specificity, F1 or AUC figure appears anywhere in this codebase, because none
> has been measured.

---

## Preprocessing

`app/ml/preprocessing.py`

| Step | What it does |
|---|---|
| `decode_image` | bytes → RGB `uint8` array |
| `find_crop_box` | bounding box of the illuminated disc (fundus images sit on a dark surround, so a low luminance threshold separates them cleanly) |
| `resize` | OpenCV `INTER_AREA` when available, Pillow bilinear otherwise |
| `normalize` | scale to 0–1, apply ImageNet statistics, emit NCHW `float32` |

ImageNet mean/std are properties of the pretrained backbones, not tunable
business configuration — which is why they are constants here rather than
database values.

OpenCV is optional. Without it the pipeline runs on NumPy + Pillow, which keeps
the service deployable in constrained environments.

---

## Quality gate

`app/ml/quality.py`

The gate exists because a blurred or badly framed photograph produces a
confident-looking but meaningless prediction. It runs **before** inference, and
a rejected image never reaches the model.

Four measurements are taken from the pixels:

| Dimension | Measurement | Rationale |
|---|---|---|
| **Blur** | variance of the 3×3 Laplacian | standard focus measure; sharp images have high edge-response variance |
| **Lighting** | mean luminance within the disc vs target, plus clipped-pixel fraction | catches both under-exposure and blown highlights |
| **Framing** | disc coverage of the frame + centroid offset from centre | catches "too far", "too close" and "off-centre" |
| **Visibility** | red-channel dominance within the disc | fundus imagery is strongly red-dominant; a frame without it is unlikely to be a retina |

Each raw measurement is mapped to a 0–1 score using **configurable** reference
values, then compared against **configurable** minimums
(`quality.thresholds`, `quality.normalisation`).

A failure returns actionable guidance, not a score:

```
IMAGE NOT SUITABLE FOR ANALYSIS

Issues:      Blur detected · Retina not centred
Recommend:   Hold the phone steady and let the camera focus.
             Centre the retina in the frame and move slightly closer.
```

The same gate runs **on-device** (Dart, `mobile/lib/services/quality_gate.dart`)
so a health worker gets an instant retake prompt while the patient is still
present. The server re-runs it on upload and remains the authority.

**This is a capture-quality check, not a clinical assessment.**

---

## Model providers

`ModelProvider` (`app/ml/providers/base.py`) is the interface everything else
depends on. Four implementations:

### `DevelopmentModelProvider` — the honest placeholder

Produces a deterministic pseudo-distribution seeded from the image's own content
hash, so demos and tests are reproducible. It exists to let the *workflow* be
built and tested before a trained model exists.

Every result it produces:

- sets `is_development_model = true`
- carries the warning `DEVELOPMENT MODEL — NOT FOR CLINICAL USE…`
- forces `requires_clinician_review` in the risk engine
- renders an unmissable banner in every UI surface

It does not detect diabetic retinopathy and must never be described as if it does.

### `UnavailableModelProvider` — failing loudly

Returned when a real model is configured but cannot be loaded. `predict()`
**raises** `MODEL NOT AVAILABLE`. This is the single most important design
decision in the pipeline: a missing model surfaces as an error, never as a
silent downgrade to placeholder output that a clinician might act on.

### `OnnxModelProvider`

ONNX Runtime. ONNX is the interchange format shared with the mobile edge
deployment, so cloud and on-device inference run the same exported graph.
Detects whether the graph already applies softmax.

### `TorchModelProvider`

PyTorch — the training-side backend, and the only one that can produce **true**
Grad-CAM (it exposes intermediate activations and gradients). Supports the
architectures from the product proposal, selected from model metadata:

`efficientnet_b0` · `efficientnet_b3` · `mobilenet_v3_large` · `mobilenet_v2`
· `resnet18` · `resnet50`

The final classifier layer is resized to the five-class scale on load.

---

## Model registry and lifecycle

`app/ml/registry.py` resolves the serving provider:

1. the `model_metadata` row marked **ACTIVE**, if one exists;
2. otherwise the provider named by `RS_MODEL_PROVIDER`.

```
REGISTER → VALIDATE → DEPLOY → ACTIVE → DEPRECATE
```

Activating a model deprecates the previous ACTIVE one, so exactly one serves at
a time. A model whose validation **failed** cannot be activated.

### Validation claims require evidence

`POST /models/{id}/validation` **rejects** `validation_status: validated` when
`validation_metrics` is empty. It is not possible to mark a model clinically
validated through this API without supplying the numbers that justify it.

`registry.status()` reports `clinically_validated` strictly from stored
metadata. It is never inferred.

---

## Grad-CAM

`app/ml/explainability.py`

For the PyTorch provider, genuine Grad-CAM: gradients of the predicted class
with respect to the final convolutional block, channel-averaged into importance
weights, ReLU'd and upscaled. Other providers supply their activation map.

Outputs:

- `heatmap.png` — colourised saliency
- `overlay.png` — heatmap composited over the retinal image
- `affected_regions[]` — coarse anatomical cells (superior/central/inferior ×
  nasal/central/temporal) with intensities
- the model version and its development status

### Interpretive limit

Shipped with **every** explanation the API returns:

> Grad-CAM indicates image regions that influenced the model's output. It is not
> a validated lesion detector and does not localise pathology.

A highlighted region is not a finding. The doctor's viewer repeats this caveat
whenever a heatmap layer is active.

An explanation failure never blocks a screening result — it is logged and the
result still returns.

---

## Risk engine

`app/services/risk_engine.py` — **fully configuration-driven**. No threshold or
category mapping is written into the code.

Ordered rules; first match wins:

| Rule | Condition | Risk |
|---|---|---|
| `quality-insufficient` | quality gate failed | Moderate |
| `proliferative-urgent` | category = proliferative | Urgent |
| `severe-high` | category = severe | High |
| `moderate-moderate` | category = moderate | Moderate |
| `mild-low` | category = mild | Low |
| `no-dr-low` | category = no DR | Low |

Three safety behaviours layer on top:

1. **Low confidence raises risk to a configured floor** — and never lowers it.
   An urgent result stays urgent regardless of confidence.
2. **A failed quality gate cannot produce a reassuring "low risk."** It matches
   the first rule and demands review.
3. **A development-model result always requires clinician review.**

Every outcome records which rule fired and a snapshot of the matched rule, so a
historical assessment stays interpretable after the configuration changes.

Editing `risk.rules` in Admin → Configuration changes behaviour immediately —
proven by `test_risk_rules_are_configuration_driven`.

---

## Referral engine

`app/services/referral_engine.py` — deliberately **separate** from the risk
engine, because risk is a clinical judgement about the patient while referral is
an operational decision about capacity and routing.

| Risk | Priority | Target | Referral raised |
|---|---|---|---|
| Urgent | urgent | 7 days | yes |
| High | consultation | 30 days | yes |
| Moderate | consultation | 90 days | yes |
| Low | routine | 365 days | no |

Routing prefers a doctor at the originating clinic. When none is available the
referral is left **unassigned** for the queue — it never invents a destination.

---

## Training a real model

The training code lives in `ml/` — deliberately outside the backend, which only
*consumes* an exported artefact.

```
ml/
├── datasets/     APTOS/EyePACS/folder adapters + synthetic generator
├── training/     training loop, model factory
├── evaluation/   metrics, confusion matrix, reports
└── export/       ONNX export with parity verification
```

### No dataset ships with this repository

The public DR datasets are license-gated and must be obtained under their own
terms: **APTOS 2019** and **EyePACS** (Kaggle, accept competition rules),
**Messidor-2** (ADCIS registration), **IDRiD** (IEEE DataPort). All use the same
0–4 scale this project uses.

### Train

```bash
cd ml
python -m training.train --data-dir data/aptos --epochs 20 --arch efficientnet_b0
```

Three choices that matter more than the architecture:

1. **Preprocessing is imported from the serving code**, not reimplemented.
   `ml/datasets/retinal_dataset.py` imports `crop_to_retina`, `resize` and the
   ImageNet constants from `backend/app/ml/preprocessing.py`, so there is no
   train/serve skew. A test asserts they are the *same object*.

2. **Class-weighted loss by default.** DR datasets are roughly 75% grade 0. An
   unweighted model collapses to predicting "no DR" for everything and still
   scores ~75% accuracy while being clinically useless.

3. **Best checkpoint is selected on macro-F1, not accuracy** — accuracy can be
   gamed by ignoring the rare, clinically important severe classes.

### Evaluate

```bash
python -m evaluation.evaluate --checkpoint models/<run>/best.pt --data-dir data/aptos
```

Reports accuracy, per-class precision/recall/F1, macro-F1, **quadratic weighted
kappa** and a **referable-DR** binary view (moderate-or-worse — the decision the
product actually makes, where sensitivity matters more than specificity).

Quadratic kappa is the headline metric because the grades are ordinal:
confusing *no DR* with *proliferative* is far worse than confusing *mild* with
*moderate*, and plain accuracy treats those identically.

### Export

```bash
python -m export.to_onnx --checkpoint models/<run>/best.pt --output models/dr-v2.onnx
```

The export is **verified before it is written** — PyTorch and ONNX Runtime must
agree on the logits to within 1e-4, or the export is refused. A silently
diverging export would produce wrong screening results with no error anywhere.

### Verifying the pipeline without a dataset

```bash
python -m datasets.make_synthetic --output data/synthetic --per-class 60
python -m training.train --data-dir data/synthetic --epochs 5
```

This generates drawn fundus-like images with a learnable lesion gradient. It
exists **only** to prove the pipeline runs end to end before committing hours to
a real dataset. The images are not retinal data, the "lesions" are geometric
artefacts, and a model trained on them has **no diagnostic meaning whatsoever**.
The generator writes a `SYNTHETIC_DATA.json` marker saying exactly that.

### After training

Register the model in **Admin → Models** with
`validation_status = not_validated`, and paste the measured numbers from
`metrics.json` — those, and only those, may be reported.

Held-out accuracy is a **development signal**. Clinical validation means
prospective evaluation on a representative population, by qualified people,
against a defined intended use. This repository does not confuse the two, and
the API will not let you either.

---

## Testing

47 tests cover the serving pipeline, plus 12 in `ml/tests/` for metrics and
dataset handling:

- preprocessing shapes, cropping, blank-frame handling
- quality gate discrimination on synthetic fundus images (blur, darkness, bad
  framing, non-retina, low resolution)
- score bounds under extreme inputs
- configuration-driven behaviour (changing thresholds flips the verdict)
- determinism, the five-class scale, probabilities summing to 1
- the development-model labelling guarantees
- `UnavailableModelProvider` raising rather than fabricating
- that `describe()` exposes **no** invented metric keys
- Grad-CAM output shape, caveat, and development-status inheritance
- risk rules, confidence floor, quality short-circuit
- referral priority mapping and unassigned routing

```bash
cd backend && python -m pytest tests/test_ml_pipeline.py tests/test_engines.py
```
