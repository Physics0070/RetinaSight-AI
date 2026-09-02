# RetinaSight AI

Admin Login for testing- chitrangadsapate7@gmail.com 

password - W-qXah0j9-0UY6@p

AI-assisted early screening for **diabetic retinopathy** using smartphone-based
retinal imaging — built around the realities of rural and low-connectivity care.

> **Scope.** RetinaSight AI is a *screening and referral-support* system. It is
> **not** an autonomous diagnostic device. Every screening is reviewed by a
> qualified clinician, and no clinical-performance claim is made anywhere in
> this repository beyond what has actually been measured.

```
PATIENT → GUIDED CAPTURE → QUALITY GATE → AI SCREENING → DR CLASSIFICATION
   → GRAD-CAM EXPLANATION → RISK + REFERRAL → CLINICIAN REVIEW → FOLLOW-UP
```

The innovation is the **workflow**, not the model alone: quality gating before
inference, offline-first capture, explainability, risk-based referral routing,
and a clinician who stays in the loop by design.

---

## Status

```
306 tests passing    157 backend · 88 frontend · 35 ML · 26 mobile
Scanner              220 files, no hardcoded config or secrets
Trained model        quadratic kappa 0.932 · referable sensitivity 0.914
```

| Component | Stack | Status |
|---|---|---|
| `backend/` | FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL | 60 endpoints, 157 tests |
| `dashboard/` | React 18 · TypeScript · Vite · Tailwind | 4 portals, 88 tests |
| `ml/` | PyTorch · ONNX · Grad-CAM | trained model included |
| `mobile/` | Flutter · SQLCipher · camera | analyzes clean, 26 tests |
| `scripts/` | hardcoding & secret scanner | runs inside the test suite |

---

## Live deployment

| Service | URL |
|---|---|
| Dashboard | https://retinasight-dashboard.onrender.com |
| API | https://retinasight-api.onrender.com — health at `/health/ready`, `/docs` disabled in production |
| Database | Managed PostgreSQL on Render, private networking only — no public endpoint |

Deployed from the committed `render.yaml` Blueprint; see
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the procedure. Two free-tier
trade-offs are live and intentional for now: the API cold-starts (30–60s)
after ~15 minutes idle, and the database is on Render's free plan, which
expires 30 days after creation — both are one-line plan upgrades in
`render.yaml` when the project outgrows them.

No credential of any kind (admin login, object-storage keys, JWT/signing
secrets, database connection string) lives in this repository — every one of
them is an environment variable set directly in Render's dashboard.

---

## The interface

**Soft neumorphism on warm clinical ivory.** The palette is the register of a
clinician's room — warm beige and paper tones, ink in a soft charcoal, and a
muted medical blue for action. Every surface is extruded from, or pressed into,
a single matte ground by a paired soft shadow: a white highlight top-left, a
warm taupe shadow bottom-right. No translucency, no blur, no border; depth comes
from the light, and each panel shares the ground's exact colour. Buttons are
raised keys that physically depress on press; inputs sit pressed into the paper.

**The chrome is light, but the imagery stays dark.** A fundus photograph is still
judged against near-black — as on a lightbox or DICOM workstation — because its
own colour is part of the read (haemorrhages and exudates are seen partly by
hue). So the viewer and capture stages keep a deep, near-black ground while the
surround stays calm and paper-warm. The clinician's room is light; the tissue
under examination sits on the dark ground its colour is measured against.

Four workspaces share the material but differ in a muted medical accent and a
subtly tinted ivory ground:

| Role | Route | Accent | Character |
|---|---|---|---|
| Health worker | `/user/*` | field blue `#2f66aa` | warmer, brighter ground for daylight |
| Doctor | `/doctor/*` | navy `#3a6098` | cleanest ivory — the colour of medical trust |
| Patient | `/patient/*` | indigo `#5f6bb0` | softest, lightest ground, larger type |
| Admin | `/admin/*` | violet-indigo `#5a4f9e` | densest, monitoring-oriented |

**No role accent may resemble a severity colour.** Accents sit in the
blue-to-indigo arc, a minimum of 35° from every severity hue, pinned by test —
chrome that looks like a severity signal invites a misread of the one signal
that must not be misread. The severity scale keeps its learned, load-bearing
hues (green → amber → orange → red) but is **deepened** for legibility on the
light ground — a contrast necessity on ivory, not a restyle.

**Fit the fundus in the frame.** Right after capture, the operator can zoom and
pan the image — buttons, mouse drag, or arrow keys — to seat the retina inside
the alignment reticle before the quality gate runs, so a photo framed slightly
too small or off-centre is salvaged rather than retaken. The doctor's review
viewer has the same controls plus layer toggles for the Grad-CAM overlay.

**Contrast is enforced by test, not by eye.** Soft low-contrast surfaces make
legibility easy to break invisibly — one such bug once shipped, white text on a
bright accent at ratio 1.58, caught only by measuring in the browser. The suite
**parses `tokens.css` itself** rather than keeping a hand-copied palette, so a
palette change cannot pass a green suite while shipping unreadable text. 43 tests
across every theme.
See [UI_DESIGN_SYSTEM.md](docs/UI_DESIGN_SYSTEM.md).

---

## Quick start

### 1. Configure

**For local development, nothing.** No application code declares an environment
value of its own — no host, no URL, no secret. Outside production the backend
reads `.env.example` at the *lowest* precedence, and Vite does the same for the
dashboard, so a fresh clone runs as-is. Create a `.env` only to override
something:

```bash
cp .env.example .env
```

**For any real deployment, this step is mandatory.** Production does not read
`.env.example`, and the service **refuses to start** on any required value that
is unset, matches a placeholder, or still equals the value published in the
example file. Generate real secrets:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Set `RS_JWT_SECRET`, `RS_JWT_REFRESH_SECRET` and `RS_STORAGE_SIGNING_SECRET` to
three *separate* generated values — reusing one across token families lets a
stolen access token be replayed as a refresh token, which is also rejected at
startup.

### 2. Backend

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
```

On macOS/Linux use `.venv/bin/pip`. Then create the schema, seed the RBAC policy
and bootstrap an administrator:

```bash
cd backend && python -m scripts.init_db
```

```bash
cd backend && python -m uvicorn app.main:app --reload
```

API docs at `http://localhost:8000/docs`, health at `/health`.

### 3. Dashboard

```bash
cd dashboard && npm install && npm run dev
```

Opens on **http://localhost:5173**.

### 4. A runnable demo (optional)

Seeds a clinic, staff, patients and completed screenings through the *real*
workflow — consent, quality gate, inference, Grad-CAM, risk and referral all
genuinely run, using real retinal images.

```bash
cd backend && python ../scripts/seed_demo.py
```

| Role | Email | Password |
|---|---|---|
| Doctor | `doctor@retinasight.ai` | `DemoPassw0rd!2026` |
| Health worker | `worker@retinasight.ai` | `DemoPassw0rd!2026` |
| Admin | `admin@retinasight.ai` | from `RS_SEED_ADMIN_PASSWORD` |

Clearly labelled synthetic data; the script refuses to run in production.

### 5. Mobile (optional)

```bash
cd mobile && flutter pub get && flutter run --dart-define=RS_API_BASE_URL=http://10.0.2.2:8000/api/v1
```

`10.0.2.2` is how the Android emulator reaches your host machine.

---

## The model

A trained EfficientNet-B0 is included (`ml/models/dr-v2.onnx`, 16 MB), so the
repository is runnable end to end. It is trained at 456px with an ordinal
objective and decides by rounding the expected grade rather than by argmax.
The previous 224px model is kept as `dr-v1.onnx` for rollback.

**Measured on 546 held-out APTOS 2019 images.** The shipped checkpoint is the
best of three seeds by kappa, so its own figures are an optimistic draw; the
across-seed column is the honest estimate of what a rerun would produce.

| Metric | Shipped checkpoint | Across 3 seeds | Previous (224px) |
|---|---|---|---|
| **Quadratic weighted kappa** | **0.932** | 0.927 ± 0.006 | 0.885 |
| **Referable-DR sensitivity** | **0.914** | 0.941 ± 0.024 | 0.891 |
| Referable-DR specificity | 0.948 | — | 0.969 |
| Accuracy | 0.833 | 0.835 ± 0.021 | 0.846 |
| Macro F1 | 0.721 | 0.701 ± 0.029 | 0.707 |

#### How far accuracy can be pushed, measured rather than guessed

A separate experiment trained three models on **one fixed split** and measured
test-time augmentation and ensembling independently
(`ml/models/ensemble-3member.json`, reproduce with `evaluation/ensemble.py`):

| Configuration | rule | **acc** | kappa | ref. sens |
|---|---|---|---|---|
| best single model + TTA | argmax | **0.8700** | 0.9266 | 0.9231 |
| ensemble ×3, no TTA | argmax | 0.8608 | 0.9169 | 0.9231 |
| **ensemble ×3, no TTA** | **expected-grade** | 0.8315 | **0.9295** | **0.9593** |

Three findings worth keeping:

- **TTA helps single models** (+0.009 to +0.017, consistent across all three) but
  **does not help the ensemble** — averaging members already supplies the
  variance reduction TTA was providing.
- **Ensembling does not raise accuracy.** The best ensemble figure stays below
  the best single model with TTA, because one member early-stopped and is
  materially weaker; the mean is dragged toward it. Ensembling does give the best
  kappa and the best referable sensitivity.
- **5-class accuracy tops out at 0.8700**, and that number is the maximum over 16
  configurations on one split — an upper bound, not an expectation. Published
  state of the art on this dataset is roughly 85–88%. Anything advertising >90%
  exact-match accuracy here is measuring something else, usually the binary
  referable decision.

⚠️ The ensemble is an **evaluation result, not a deployed capability**. The
product serves a single ONNX graph, and no claim in the product rests on it.

**Read these honestly.**

- **Kappa is the headline** because the grades are ordinal — confusing *no DR*
  with *proliferative* is far worse than *mild* with *moderate*, and kappa
  penalises by squared distance. The +0.042 gain over the 224px model is roughly
  seven times the seed-to-seed spread, so it is a real effect, not noise.
- **Accuracy went slightly down, and that is expected.** Rounding the expected
  grade trades exact-match accuracy for smaller-distance errors. Accuracy is
  also the weakest metric here: 49% of APTOS is grade 0, so predicting "no DR"
  for everything scores 49% while being clinically useless.
- **Specificity fell from 0.969 to 0.948.** A more sensitive model refers more
  people, some of them unnecessarily. On roughly 325 non-referable cases that is
  about seven extra referrals — the right trade for a screening tool, but it is
  a real cost borne by patients and clinics, not a free win.

**Per-class recall (shipped checkpoint):** no DR 0.97 · mild 0.69 ·
moderate 0.70 · **severe 0.68** · proliferative 0.68.

Severe recall moved from 0.43 to 0.68 — the single largest improvement, and the
weakness the ordinal objective was chosen to attack. It still rests on only 28
validation examples, so treat it as directional. That uncertainty is exactly why
the risk engine forces clinician review on every case rather than trusting model
confidence.

> These are **development metrics on a held-out split** — not clinical
> validation. The model is registered as `not_validated`, and the API rejects a
> "validated" status submitted without evidence.

**The decision rule ships inside the graph.** A model trained with the ordinal
objective is measured by rounding its expected grade, which disagrees with
argmax on a meaningful fraction of cases. Serving this checkpoint by argmax
would score referable sensitivity 0.891 — indistinguishable from the model it
replaces — while the registry advertised 0.914. So the exported ONNX graph emits
the decided grade as a third output alongside the logits and CAM, and every
consumer reads it. `ml/tests/test_train_export_serve.py` pins this.

### Training your own

No dataset ships here; the public DR datasets are licence-gated. See
[ml/README.md](ml/README.md) and
[TRAINING_A_REAL_MODEL.md](docs/TRAINING_A_REAL_MODEL.md).

```bash
cd ml

# Verify the pipeline without a real dataset
python -m datasets.make_synthetic --output data/synthetic --per-class 60
python -m training.train --data-dir data/synthetic --epochs 5

# Real data
python -m datasets.prepare_aptos --data-dir data/aptos
python -m datasets.cache_preprocessed --data-dir data/aptos --output data/aptos_456 --image-size 456
python -m training.train --data-dir data/aptos_456 --image-size 456 --batch-size 8
python -m evaluation.evaluate --checkpoint models/<run>/best.pt --data-dir data/aptos_456
python -m export.to_onnx --checkpoint models/<run>/best.pt --output models/dr-v2.onnx
```

Three choices that matter more than the architecture:

1. **Preprocessing is imported from the serving code**, not reimplemented, so
   there is no train/serve skew. A test asserts they are the same objects.
2. **Class-weighted, ordinal-aware loss.** DR datasets are ~75% grade 0, and
   plain cross-entropy ignores the ordering the metric cares about.
3. **Checkpoint selection on kappa**, the metric the task is judged by. Selecting
   on macro-F1 — which swings on a 28-sample class — cost a measurably better
   checkpoint in testing.

**Single runs are not evidence here.** `evaluation/compare_runs.py` runs a
configuration across seeds and reports mean ± spread, because the run-to-run
variance on this validation set is larger than most improvements worth claiming.

### Serving it

1. `pip install -r backend/requirements-ml.txt`
2. Put the artefact in `RS_MODEL_DIR` (defaults to `ml/models`)
3. `python scripts/register_trained_model.py`, or **Admin → Models**

If a real model is configured but cannot load, the system reports
**MODEL NOT AVAILABLE** — it never silently falls back to placeholder output.

---

## Database

Local development defaults to **SQLite** (nothing to install). Production uses
**PostgreSQL**; the models are portable and the same migrations apply to both.

```bash
export RS_DATABASE_URL="postgresql+psycopg://user:password@host:5432/retinasight"
cd backend && python -m alembic upgrade head
```

## Object storage

Retinal images are patient data. They never sit in the database and are never
publicly reachable — local filesystem in development, any S3-compatible bucket in
production, both read only through short-lived signed URLs.

The backend **refuses to start** in production with filesystem storage: a
container filesystem is ephemeral, so patient images would be lost on deploy.

---

## Testing

```bash
cd backend    && python -m pytest          # 157
cd dashboard  && npm test                  # 87
cd ml         && python -m pytest tests/   # 35
cd mobile     && flutter test              # 26
python scripts/check_no_hardcoding.py
```

---

## Documentation

| Document | Covers |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System shape, layering, data flow |
| [API.md](docs/API.md) | Endpoint reference and conventions |
| [DATABASE.md](docs/DATABASE.md) | Entities, relationships, migrations |
| [ML_PIPELINE.md](docs/ML_PIPELINE.md) | Preprocessing, quality gate, inference, Grad-CAM |
| [OFFLINE_SYNC.md](docs/OFFLINE_SYNC.md) | Offline-first design and idempotent sync |
| [SECURITY.md](docs/SECURITY.md) | Authentication, storage, auditing, known gaps |
| [RBAC.md](docs/RBAC.md) | Roles, permissions, enforcement model |
| [UI_DESIGN_SYSTEM.md](docs/UI_DESIGN_SYSTEM.md) | Glass material, tokens, contrast, accessibility |
| [TESTING.md](docs/TESTING.md) | What is tested and how to extend it |
| **[TRAINING_A_REAL_MODEL.md](docs/TRAINING_A_REAL_MODEL.md)** | **Getting a trained model into the system** |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Render blueprint, environment setup, rollback |

---

## Repository layout

```
retinasight-ai/
├── backend/          FastAPI service, ML serving, migrations, tests
│   └── app/
│       ├── api/          routers + authorization dependencies
│       ├── core/         config, security, logging, errors, rate limiting
│       ├── domain/       enums, RBAC matrix, config defaults
│       ├── ml/           preprocessing, quality gate, providers, Grad-CAM
│       ├── models/       SQLAlchemy entities
│       ├── services/     business logic
│       └── storage/      object-storage providers
├── dashboard/        React portals (admin · health worker · patient · doctor)
├── ml/               training, evaluation, ONNX export, calibration
├── mobile/           Flutter health-worker app (offline-first)
├── scripts/          scanner, seeding, model registration
└── docs/
```

---

## Clinical safety notes

Enforced in code and covered by tests, not just documented:

1. **Consent gates screening.** A session cannot start without recorded consent.
2. **The quality gate is a hard precondition.** A rejected image never reaches
   the model — and the gate is calibrated against *real* fundus photographs, not
   synthetic approximations.
3. **A clinician reviews every screening.** A product invariant, not a setting.
4. **Administration ≠ clinical authority.** Admins do not hold `CLINICAL_REVIEW`.
5. **Low confidence raises risk.** It never lowers it.
6. **Grad-CAM is not a lesion detector.** Its caveat travels with every
   explanation the API returns.
7. **Severity is never signalled by colour alone** — glyph, label and scale
   position all carry it.
