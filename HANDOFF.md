# HANDOFF

Session handoff for RetinaSight AI. Written to be read cold — no prior context
assumed.

---

## 1. The goal

Build **RetinaSight AI**: AI-assisted early screening for diabetic retinopathy
using smartphone-based retinal imaging, for rural and low-connectivity care.

The deliverable is a working multi-role platform — guided capture → quality gate
→ AI screening → Grad-CAM explanation → risk-based referral → clinician review —
**not** an autonomous diagnostic device. A clinician reviews every screening, and
no clinical-performance claim is made beyond what has actually been measured.

Repository: <https://github.com/Physics0070/RetinaSight-AI>

---

## 2. Current state

### Verified working

```
264 tests passing    133 backend · 74 frontend · 31 ML · 26 mobile
Scanner              201 files, no hardcoded config or secrets
Build                typecheck clean, production build succeeds
Migration            applies and reverses cleanly (25 tables)
Flutter              flutter analyze: 0 issues
```

**Backend** — 60 endpoints, 25 tables. Argon2id + JWT with refresh rotation and
replay detection; RBAC re-resolved from the database on every request; patient
isolation denied *and* audited; admin does not hold `CLINICAL_REVIEW`; signed-URL
object storage that refuses ephemeral disks in production; 18-state screening
machine with consent and quality gates as hard preconditions; idempotent offline
sync; login rate limiting; audit log; background worker.

**Dashboard** — four separate portals (admin, health worker, patient, doctor) in
a futuristic glass design system. Retinal viewer with layers/zoom/pan/compare,
fully keyboard-operable. Risk severity carried by four redundant cues.

**ML** — quality gate calibrated against real fundus photographs, preprocessing
shared with training, ONNX/PyTorch/development providers, Grad-CAM baked into the
exported graph, separate risk and referral engines driven by database config.

**Mobile** — Flutter app: SQLCipher-encrypted store, on-device quality gate,
guided capture, connectivity-aware background sync. Analyzes clean, 26 tests
pass. **Never run on a device or emulator.**

### The model

Shipped artefact `ml/models/dr-v1.onnx` (16 MB), trained on APTOS 2019, measured
on 546 held-out images:

| Metric | Value |
|---|---|
| Quadratic kappa | 0.885 |
| Referable-DR sensitivity | 0.891 |
| Accuracy | 0.846 |
| Macro F1 | 0.707 |
| Severe-class recall | **0.43** |

Registered as `not_validated`. It is a development result, not clinical
validation.

### Open

> **All four steps in §6 are now DONE.** §6 is kept as the record of what was
> asked and how each was resolved — read it before re-opening any of them.
> Live status lives in [CHECKLIST.md](CHECKLIST.md).

Genuinely still open, and none of it fakeable from this machine:

- **The backend suite has only ever run against SQLite.** Neither `psql` nor
  `docker` is installed here. Portability is structural — no raw SQL, no
  SQLite-only types, `render_as_batch` migrations — but it is **not verified**.
  This is the highest-value open item: it is the difference between "should work
  on PostgreSQL" and "does".
- **The Flutter app has never run on a device or emulator.** `flutter devices`
  offers only Windows, Chrome and Edge; there is no Android emulator installed.
  The 26 tests pass and `flutter analyze` is clean, but camera capture and the
  on-device quality gate are unexercised on real hardware.
- **The Kaggle API token pasted into chat during this project must be rotated.**
  Treat it as public.
- Deployment config exists (`render.yaml`, `docs/DEPLOYMENT.md`) but nothing is
  deployed.
- The 5-class accuracy target of >90% was **not reached** — 0.8700 is the
  measured ceiling. See §6 Step 3; this is a limit of the task and dataset, not
  an unfinished piece of work.

---

## 3. Active files

### Where the important logic lives

| Concern | File |
|---|---|
| Quality gate (recently recalibrated) | `backend/app/ml/quality.py` |
| Clinical thresholds & rules (seed defaults) | `backend/app/domain/config_defaults.py` |
| Runtime config source of truth | `backend/app/services/config_service.py` |
| Risk engine | `backend/app/services/risk_engine.py` |
| Referral engine | `backend/app/services/referral_engine.py` |
| Screening state machine | `backend/app/services/screening_state_machine.py` |
| Authorization | `backend/app/api/deps.py`, `backend/app/services/rbac_service.py` |
| Model resolution | `backend/app/ml/registry.py` |
| ONNX provider (reads CAM output) | `backend/app/ml/providers/onnx_provider.py` |

### Design system (the colour-scheme task lives here)

| Concern | File |
|---|---|
| **All colour tokens** | `dashboard/src/design-system/tokens/tokens.css` |
| Glass material, ambient light, grid | `dashboard/src/styles/global.css` |
| Buttons/inputs/panels | `dashboard/src/design-system/components/primitives.tsx` |
| Risk display (colour + glyph + label) | `dashboard/src/design-system/risk/RiskDisplay.tsx` |
| Contrast tests (must stay green) | `dashboard/src/test/contrast.test.tsx` |

**A colour change should only need `tokens.css`.** Components contain no colour
literals. The exceptions are the fundus illustration in
`dashboard/src/app/LoginPage.tsx` and the Grad-CAM colour ramp in
`backend/app/ml/explainability.py` — both depict real anatomy/data, not theme.

### ML pipeline

| Concern | File |
|---|---|
| Training loop, checkpoint selection | `ml/training/train.py` |
| Ordinal loss | `ml/training/losses.py` |
| Dataset adapters, augmentation | `ml/datasets/retinal_dataset.py` |
| Image cache (must be complete) | `ml/datasets/cache_preprocessed.py` |
| Metrics | `ml/evaluation/metrics.py` |
| Multi-seed comparison | `ml/evaluation/compare_runs.py` |
| Quality-gate calibration | `ml/evaluation/calibrate_quality_gate.py` |
| ONNX export + CAM wrapper | `ml/export/to_onnx.py`, `ml/export/cam_wrapper.py` |

### Guardrails

| Concern | File |
|---|---|
| Hardcoding scanner (+ allowlist) | `scripts/check_no_hardcoding.py` |
| Scanner runs inside the test suite | `backend/tests/test_no_hardcoding.py` |
| Demo seeding | `scripts/seed_demo.py` |
| Model registration | `scripts/register_trained_model.py` |

### Environment (this machine)

```
Python 3.12.9 + venv at backend/.venv     torch 2.6.0+cu124, CUDA available
Node 25.9                                  GPU: RTX 4050 Laptop, 6 GB
Git      D:\tools\git\cmd\git.exe          portable, NOT on PATH
Flutter  D:\tools\flutter\bin\flutter.bat  3.47.1, portable, NOT on PATH
Dataset  ml/data/aptos (3662), aptos_224, aptos_456   git-ignored
```

---

## 4. Changes made this session

Built the entire project from an empty directory. Commits (17, split evenly
between the two authors) are individually descriptive; the notable items:

1. **Backend, dashboard, mobile, ML pipeline** — full build, described above.
2. **Trained a real model** on APTOS 2019 and wired it through export → registry
   → serving.
3. **Quality gate recalibrated against real fundus photographs.** It previously
   rejected 100% of real images (see §5).
4. **Grad-CAM made to work under ONNX** by baking class-activation maps into the
   exported graph — ONNX Runtime has no gradients, so the served model was
   returning blank heatmaps.
5. **Futuristic glass UI** across all four portals, plus 30 WCAG contrast tests.
6. **Checkpoint selection changed from macro-F1 to quadratic kappa**, and
   multi-seed comparison added.
7. **Rate limiting enforced** (it was configured but decorative).
8. **Deployment config** — `render.yaml`, background worker, runbook.
9. **Documentation** — 11 documents plus this handoff.

---

## 5. Failed attempts and dead ends

**Do not repeat these.**

### Calibrating the quality gate on synthetic images

The gate's thresholds were tuned against synthetically generated fundus-like
images. Real photographs behave completely differently — the retinal disc fills
**~0.79** of a real frame, not the ~0.42 assumed, and real retinal tissue is far
smoother than drawn texture. The gate rejected **100% of real APTOS images**;
no screening could ever have completed.

Fixed by calibrating against 250 real images
(`ml/evaluation/calibrate_quality_gate.py`). **Any future threshold change must be
validated against real images, and against degraded copies of them** — a gate
that accepts everything is as broken as one that accepts nothing.

### Measuring sharpness without normalising scale

Variance of the Laplacian is scale-dependent, so the same photograph scored
differently at 2000px and 224px — meaning the verdict depended on the phone's
sensor resolution. Now measured at a fixed `analysis_long_edge` (512px).

### Selecting checkpoints on macro-F1

Macro-F1 weights a 28-sample validation class equally with a 270-sample one, so
it swings hard. Two runs of the *same* configuration peaked at 0.720 and 0.669;
one early-stopped at epoch 10 having peaked at epoch 4 while a better checkpoint
was still ahead. **Select on the metric the task is judged by (kappa).**

### Trusting a single training run

Run-to-run variance on this validation set exceeds most improvements worth
claiming. An early 456px run reported kappa 0.926 and was believed; it was
inflated by an incomplete cache and a different split. **Use
`ml/evaluation/compare_runs.py` and report mean ± spread.**

### Caching with too many workers

`cache_preprocessed` with `--workers 10` at 456px silently dropped **60 of 3662**
images to memory pressure, skewing the class balance. Failures were swallowed as
a bare `False`. Now they report the exception and an incomplete cache exits
non-zero. **Use `--workers 4` at 456px.**

### Tailwind arbitrary classes for colour

`text-[var(--rs-accent-ink)]` is ambiguous between colour and font-size; Tailwind
emitted nothing and the primary button inherited near-white body ink — white on
cyan at contrast **1.58**. **Set colour via inline style, or use
`text-[color:var(...)]`.** Pinned by `dashboard/src/test/contrast.test.tsx`.

### Reserved TLDs in seeded email addresses

`admin@retinasight.local` passed creation but `.local` is RFC-reserved and fails
email validation, so the bootstrap administrator **could never sign in**. Same
applies to `.test`, `.example`, `.invalid`.

### Relative paths resolved against the process working directory

`RS_MODEL_DIR=./ml/models` resolved to `backend/ml/models`, so the service
reported `MODEL NOT AVAILABLE` while the artefact sat in `ml/models`. Relative
config paths now resolve against the repository root.

### Shell/tooling gotchas on this machine

- PowerShell's `Set-Location` does **not** change .NET's working directory, so
  `[System.IO.File]::ReadAllText("relative\path")` silently targets the wrong
  place. Use `(Resolve-Path …).Path`.
- `Remove-Item` on paths containing spaces was blocked by a safety check; use
  `[System.IO.File]::Delete()`.
- The Bash tool returned empty output with exit 1 for much of the session. Use
  PowerShell.
- `Invoke-WebRequest` downloads at ~0.2 MB/s because of progress rendering. Use
  `curl.exe -L -C -` (38× faster, and resumable).
- Route order matters in FastAPI: `/images/blob` must be declared before
  `/images/{image_id}` or the literal path is swallowed.

---

## 6. Next steps — ALL RESOLVED

Kept as the record of what was asked and how each was answered.

| Step | Outcome |
|---|---|
| 1 — Ship or discard the 456px model | **Shipped** as `dr-v2`, active at 456×456, `not_validated`. The decision rule is baked into the ONNX graph as a third output — serving it by argmax scored referable sensitivity 0.891 while the registry advertised 0.914 |
| 2 — Colour scheme | **Done.** Spectral accents on neutral graphite. Uncovered that `transition: background` latched the old value on a custom-property change, so all four per-role grounds had been written but never shipped |
| 3 — Accuracy >90% | **Not reachable honestly. 0.8700 measured.** See below — this is a limit of the task, not unfinished work |
| 4 — Eliminate hardcoding | **Done.** 9 blanket file exemptions → 5 narrow `(path, rule)` pairs; values removed rather than excused |

**Before re-attempting Step 3, read this:** the obvious move — ensemble the
three existing checkpoints — is invalid. Each was trained with a seed that also
drove the train/val split, so of seed 143's 546 validation images, 462 sit in
seed 42's *training* set; only 15 images were held out by all three. Averaging
them scores against data they partly trained on. `split_seed` is now separate
from `seed`, and `evaluation/ensemble.py` refuses members whose splits disagree.

The measured ceiling, on one fixed split with TTA and ensembling separated:
**0.8700** 5-class accuracy (best single model + TTA + argmax), itself the
maximum over 16 configurations and therefore an upper bound. Kappa **0.9295**
and referable sensitivity **0.9593** do exceed 90% and are different metrics.
TTA helps single models but not the ensemble; ensembling helps kappa but not
accuracy. Full grid: `ml/models/ensemble-3member.json`.

---

### Step 1 — Ship or discard the 456px model *(RESOLVED — shipped)*

The experiment is complete and measured over three seeds:

| Metric | Shipped (224px) | 456px + ordinal (3 seeds) | Change |
|---|---|---|---|
| **Quadratic kappa** | 0.885 | **0.9271 ± 0.0062** | **+0.042** ✅ |
| **Referable sensitivity** | 0.891 | **0.9412 ± 0.0240** | **+0.050** ✅ |
| Accuracy | 0.846 | 0.8351 ± 0.0211 | **−0.011** ⚠️ |
| Macro F1 | 0.707 | 0.7013 ± 0.0285 | −0.006 |

The kappa gain is **7× the seed spread**, so it is real, not noise. But **raw
accuracy went slightly down** — expected, because rounding the expected grade
trades exact-match accuracy for smaller-distance errors.

**This matters for the accuracy target in Step 3.** The ordinal work moves kappa
and clinical sensitivity up while moving raw accuracy marginally *down*.

To ship it: evaluate the best seed → `export.to_onnx` → verify it serves →
`scripts/register_trained_model.py` → update README.

### Step 2 — Change the colour scheme *(RESOLVED — done)*

Edit `dashboard/src/design-system/tokens/tokens.css` only. Four role themes:
worker (teal), doctor (cyan), patient (amber), admin (indigo), plus the shared
risk scale and the `--rs-ambient` gradients.

**Constraint:** `npm test` must stay green — 30 contrast tests assert real WCAG
ratios. If a new palette fails them, the palette is wrong, not the tests. Update
the expected token values in `contrast.test.tsx` to match the new scheme and
confirm every ratio still clears AA.

### Step 3 — Accuracy target (>90%) *(RESOLVED — 0.8700, target not reachable)*

**Read this before starting.** Current 5-class accuracy is 0.835–0.846.

Reaching **>90% accuracy on the 5-class task is very unlikely** on APTOS with a
single model — published state of the art is roughly 85–88%. The metrics that
already exceed 90% are quadratic kappa (0.927) and the referable-DR binary
decision (~95%).

Legitimate ways to push 5-class accuracy, in order of expected value:

1. **Ensemble the three trained seeds** — averaging softmax typically adds
   1–2 points. Checkpoints are already in `ml/models/`.
2. **Test-time augmentation** — flips/rotations, usually +0.5–1 point.
3. **Add EyePACS** (88,702 images, 24× APTOS) — the largest remaining lever, and
   the only one likely to move severe-class recall off 0.43.
4. **Tune the decision rule** — `--argmax-decision` optimises exact-match
   accuracy at the cost of kappa. This is a genuine trade-off, not a free win.
5. **EfficientNet-B3/B4** at 456px — only worth it after the above.

**Do not** reach the target by testing on training data, by quietly redefining
"accuracy" as the binary referable decision, or by reporting the best seed as if
it were typical. If 90% is not reached, say so and report what was.

### Step 4 — Eliminate remaining hardcoding *(RESOLVED — done)*

The scanner passes across 201 files with **9 allowlisted paths**, each with a
written reason (`scripts/check_no_hardcoding.py`, `ALLOWLIST`).

To reduce the list further:

- `backend/app/core/config.py`, `dashboard/src/lib/config.ts`,
  `mobile/lib/core/config.dart` hold localhost/emulator **defaults**. These can
  be made required-with-no-default so a missing value fails loudly. Trade-off:
  `npm run dev` and `uvicorn` stop working without a `.env`.
- `backend/app/domain/config_defaults.py` and `rbac_matrix.py` are **seed**
  values; the database is the runtime source of truth. Removing them means an
  empty database has no clinical rules and no RBAC policy at all. Deliberate
  design — changing it needs care.
- `scripts/seed_demo.py` uses known demo credentials by design and refuses to
  run in production.

**Genuinely achievable:** get the allowlist from 9 down to about 4 by making the
three config layers required-without-defaults. The remaining entries are
structural, and removing them would make the system worse, not less hardcoded.

### Also outstanding

- **Rotate the Kaggle API token** — it appeared in a screenshot during this
  session.
- Run the Flutter app on a real device or emulator; it has only ever been
  analyzed and unit-tested.
- Run the backend suite against PostgreSQL; it has only run on SQLite.
