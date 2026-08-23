# RetinaSight AI

AI-assisted early screening for **diabetic retinopathy** using smartphone-based
retinal imaging — built around the realities of rural and low-connectivity care.

> **Scope.** RetinaSight AI is a *screening and referral-support* system. It is
> **not** an autonomous diagnostic device. Every screening is reviewed by a
> qualified clinician, and no clinical-performance claim is made anywhere in
> this repository, because none has been measured.

```
PATIENT → GUIDED CAPTURE → QUALITY GATE → AI SCREENING → DR CLASSIFICATION
   → GRAD-CAM EXPLANATION → RISK + REFERRAL → CLINICIAN REVIEW → FOLLOW-UP
```

The innovation is the **workflow**, not the model alone: quality gating before
inference, offline-first capture, explainability, risk-based referral routing,
and a clinician who stays in the loop by design.

---

## What is here

| Component | Stack | Status |
|---|---|---|
| `backend/` | FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL | **122 tests passing** |
| `dashboard/` | React 18 · TypeScript · Vite · Tailwind | **44 tests passing**, builds clean |
| `ml/` | PyTorch training · evaluation · ONNX export | Pipeline complete; **no dataset shipped** |
| `mobile/` | Flutter · SQLCipher · camera | Written; **not compiled** (see caveat) |
| `scripts/` | Hardcoding & secret scanner | **149 files scanned, clean** |
| `docs/` | Architecture, API, security, ML, sync | — |

### Honest status

- **The ML model is a labelled placeholder.** `DevelopmentModelProvider`
  produces deterministic, structurally valid output so the pipeline can be
  exercised end to end. It carries **no diagnostic meaning**, is flagged
  `is_development_model` on every response, and surfaces an unmissable
  "NOT FOR CLINICAL USE" banner in the UI. Marking a model *validated* without
  accompanying metrics is **rejected by the API**.
- **The Flutter app has not been compiled.** No Dart SDK was available in the
  build environment. The source is complete and its logic mirrors the tested
  backend state machine, but treat it as unverified until you run
  `flutter analyze && flutter test`.
- **Nothing is deployed.** Deployment configuration was deliberately left out
  of this pass.

---

## Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Python | 3.11+ | backend, ML pipeline |
| Node.js | 20+ | dashboard |
| PostgreSQL | 14+ | production database (SQLite is used for local dev) |
| Flutter | 3.19+ | mobile app only |

Heavy ML dependencies (PyTorch, ONNX Runtime, OpenCV) are **optional** — the
backend runs fully without them.

---

## Quick start

### 1. Configure

```bash
cp .env.example .env
```

Generate real secrets — never ship the defaults:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Set `RS_JWT_SECRET`, `RS_JWT_REFRESH_SECRET` and `RS_STORAGE_SIGNING_SECRET` to
separate generated values.

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
```

On macOS/Linux use `.venv/bin/pip` instead.

Create the schema, seed the RBAC policy and bootstrap an administrator:

```bash
cd backend && python -m scripts.init_db
```

Run it:

```bash
cd backend && python -m uvicorn app.main:app --reload
```

API docs are then at `http://localhost:8000/docs`, health at `/health`.

### 3. Dashboard

```bash
cd dashboard && npm install && npm run dev
```

Opens on `http://localhost:5173`. Sign in with the bootstrap administrator from
`RS_SEED_ADMIN_EMAIL` / `RS_SEED_ADMIN_PASSWORD`.

### 4. Mobile (optional)

```bash
cd mobile && flutter pub get && flutter run --dart-define=RS_API_BASE_URL=http://10.0.2.2:8000/api/v1
```

`10.0.2.2` is how the Android emulator reaches your host machine.

---

## Database

Local development defaults to **SQLite** so there is nothing to install. Production
uses **PostgreSQL** — the models are written portably and the same migrations
apply to both.

```bash
# point at PostgreSQL
export RS_DATABASE_URL="postgresql+psycopg://user:password@host:5432/retinasight"

cd backend && python -m alembic upgrade head
```

Migrations live in `backend/migrations/`. They are generated with
`alembic revision --autogenerate -m "description"` and reviewed before commit.

---

## Object storage

Retinal images are patient data. They never sit in the database and are never
publicly reachable:

- **Development:** local filesystem, served only through short-lived
  HMAC-signed URLs.
- **Production:** any S3-compatible bucket (AWS, Cloudflare R2, MinIO,
  Backblaze), written with a private ACL and read through presigned URLs.

The backend **refuses to start** in production with filesystem storage, because
a container filesystem is ephemeral and patient images would be lost on deploy.

---

## Training a model

The system ships with a labelled development placeholder active — **no trained
weights are included**, and no retinal dataset is bundled (the public ones are
license-gated; see [ml/README.md](ml/README.md) for how to obtain them).

```bash
cd ml

# Verify the pipeline end-to-end without a real dataset
python -m datasets.make_synthetic --output data/synthetic --per-class 60
python -m training.train --data-dir data/synthetic --epochs 5

# Train on real data
python -m training.train --data-dir data/aptos --epochs 20 --arch efficientnet_b0
python -m evaluation.evaluate --checkpoint models/<run>/best.pt --data-dir data/aptos
python -m export.to_onnx --checkpoint models/<run>/best.pt --output models/dr-v1.onnx
```

Training imports its preprocessing directly from the serving code, so there is
no train/serve skew. Loss is class-weighted by default (DR datasets are ~75%
grade 0) and the best checkpoint is chosen on macro-F1, not accuracy.

### Serving it

1. Install the ML extras: `pip install -r backend/requirements-ml.txt`
2. Place the artefact in `RS_MODEL_DIR` (`.onnx` or `.pt`)
3. Register it in **Admin → Models**, paste the measured numbers from
   `metrics.json`, then advance `REGISTER → VALIDATE → DEPLOY → ACTIVE`

If a real model is configured but cannot be loaded, the system reports
**MODEL NOT AVAILABLE** — it never silently falls back to placeholder output.

> Held-out metrics are a development signal, not clinical validation. Register
> a newly trained model as `not_validated` and leave it there until real
> prospective validation exists. The API rejects a "validated" status submitted
> without accompanying metrics.

---

## Testing

```bash
cd backend && python -m pytest
```

```bash
cd dashboard && npm test
```

```bash
cd mobile && flutter test
```

Hardcoding, secret and Firebase scan:

```bash
python scripts/check_no_hardcoding.py --verbose
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
| [SECURITY.md](docs/SECURITY.md) | Authentication, storage, auditing, threat notes |
| [RBAC.md](docs/RBAC.md) | Roles, permissions, enforcement model |
| [UI_DESIGN_SYSTEM.md](docs/UI_DESIGN_SYSTEM.md) | Tokens, contextual morphism, accessibility |
| [TESTING.md](docs/TESTING.md) | What is tested and how to extend it |
| **[TRAINING_A_REAL_MODEL.md](docs/TRAINING_A_REAL_MODEL.md)** | **Step-by-step: getting a real trained model into the system** |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Render blueprint, environment setup, rollback |

---

## Repository layout

```
retinasight-ai/
├── backend/          FastAPI service, ML pipeline, migrations, tests
│   ├── app/
│   │   ├── api/          routers + authorization dependencies
│   │   ├── core/         config, security, logging, errors
│   │   ├── db/           engine, session, declarative base
│   │   ├── domain/       enums, RBAC matrix, config defaults
│   │   ├── ml/           preprocessing, quality, providers, Grad-CAM
│   │   ├── models/       SQLAlchemy entities
│   │   ├── repositories/ data access
│   │   ├── schemas/      Pydantic contracts
│   │   ├── services/     business logic
│   │   └── storage/      object-storage providers
│   ├── migrations/   Alembic
│   └── tests/
├── dashboard/        React portals (admin · health worker · patient · doctor)
│   └── src/
│       ├── app/           shell, routing, guards
│       ├── design-system/ tokens, primitives, imaging, risk
│       ├── lib/           API client, auth, types
│       └── portals/       one directory per role
├── mobile/           Flutter health-worker app (offline-first)
├── scripts/          hardcoding scanner, utilities
└── docs/
```

---

## Clinical safety notes

These are enforced in code and covered by tests, not just documented:

1. **Consent gates screening.** A session cannot start without recorded consent.
2. **The quality gate is a hard precondition.** A rejected image never reaches
   the model.
3. **A clinician reviews every screening.** This is a product invariant, not a
   per-case setting.
4. **Administration ≠ clinical authority.** Platform admins do not hold
   `CLINICAL_REVIEW`; only a doctor signs off a case.
5. **Low confidence raises risk.** It never lowers it.
6. **Grad-CAM is not a lesion detector.** Its interpretive caveat travels with
   every explanation the API returns.
