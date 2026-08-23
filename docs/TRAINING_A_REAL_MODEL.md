# Getting a real model into RetinaSight AI

Everything on the machine side is built and verified. What remains needs **you**,
because it involves accounts and licences I cannot accept on your behalf.

Steps 1 and 2 are yours. Steps 3–6 I can run for you once step 2 is done.

---

## Step 1 — Get a dataset licence *(only you can do this)*

The public diabetic-retinopathy datasets are all gated behind an account and a
rules acceptance. Pick one:

| Dataset | Images | Size | Where |
|---|---|---|---|
| **APTOS 2019** ← recommended | 3,662 | ~10 GB | [kaggle.com/c/aptos2019-blindness-detection](https://www.kaggle.com/c/aptos2019-blindness-detection) |
| EyePACS | 88,702 | ~82 GB | [kaggle.com/c/diabetic-retinopathy-detection](https://www.kaggle.com/c/diabetic-retinopathy-detection) |
| Messidor-2 | 1,748 | ~3 GB | [adcis.net/en/third-party/messidor2](https://www.adcis.net/en/third-party/messidor2/) |
| IDRiD | 516 | ~1 GB | [ieee-dataport.org/open-access/indian-diabetic-retinopathy-image-dataset-idrid](https://ieee-dataport.org/open-access/indian-diabetic-retinopathy-image-dataset-idrid) |

**Start with APTOS.** It is the best size-to-value ratio for your GPU, and it
trains in well under an hour.

What to do:

1. Create a Kaggle account (free).
2. Open the APTOS competition page.
3. Click **Join Competition** and accept the rules. *Downloads fail with a 403
   until you do this — it is the licence acceptance.*

---

## Step 2 — Put your Kaggle API token on this machine

1. Go to <https://www.kaggle.com/settings/account>
2. Under **API**, click **Create New Token** — it downloads `kaggle.json`
3. Move it to:

```
C:\Users\Soham\.kaggle\kaggle.json
```

Create the `.kaggle` folder if it does not exist. That file is your credential —
it is already covered by `.gitignore` and must never be committed.

**Tell me when this is done and I will take it from there.**

---

## Step 3 — Download *(I can run this)*

```bash
pip install kaggle
kaggle competitions download -c aptos2019-blindness-detection -p ml/data/aptos
```

Then unzip in place. The expected result:

```
ml/data/aptos/
├── train.csv          id_code,diagnosis
└── train_images/      *.png
```

The dataset loader already understands this layout — no conversion needed.

---

## Step 4 — Train *(I can run this)*

```bash
cd ml
python -m training.train --data-dir data/aptos --epochs 25 --arch efficientnet_b0 --batch-size 16
```

On your RTX 4050 this is roughly **20–35 minutes** for APTOS at 25 epochs.

Writes to `ml/models/<run>/`:

| File | Contents |
|---|---|
| `best.pt` | best checkpoint, chosen on macro-F1 |
| `metrics.json` | the real measured numbers |
| `history.json` | per-epoch curves |

### If accuracy looks high but macro-F1 is low

That is the classic DR failure: the model has collapsed to predicting "no DR"
for everything (~75% of APTOS is grade 0). Class weighting is on by default to
prevent it. If it still happens, try:

```bash
--arch efficientnet_b3 --image-size 300 --epochs 40 --learning-rate 1e-4
```

---

## Step 5 — Evaluate and export *(I can run this)*

```bash
python -m evaluation.evaluate --checkpoint models/<run>/best.pt --data-dir data/aptos
python -m export.to_onnx --checkpoint models/<run>/best.pt --output models/dr-v1.onnx
```

The export refuses to write unless PyTorch and ONNX Runtime agree on the logits
to within 1e-4, so a silently broken artefact cannot reach production.

---

## Step 6 — Register and activate *(you, in the admin portal)*

The artefact must sit in the directory `RS_MODEL_DIR` points at. The default
resolves to `<repo>/ml/models`, which is exactly where step 5 writes — so no
copying is needed.

1. Sign in as an administrator → **Admin → Models → Register model**

   | Field | Value |
   |---|---|
   | Name | `retinasight-dr` |
   | Version | `v1` |
   | Framework | `ONNX` |
   | Deployment target | `Cloud` |
   | Architecture | `efficientnet_b0` |
   | Artefact path | `dr-v1.onnx` |

2. Open `ml/models/<run>/metrics.json` and paste the measured numbers into
   **Validation**. Leave the status as **not validated**.

3. Set the lifecycle status to **ACTIVE**. The previously active model is
   deprecated automatically.

4. Confirm on **Admin → System health**:
   - Model: **Loaded**
   - `Development model` badge: **gone**
   - Validation: **not clinically validated** ← correct and expected

The service picks the new model up immediately. No redeploy.

---

## Also needed for full production readiness

Independent of the model:

| Item | Why |
|---|---|
| **Generate real secrets** | `RS_JWT_SECRET`, `RS_JWT_REFRESH_SECRET`, `RS_STORAGE_SIGNING_SECRET` — the defaults are deliberately marked insecure. `python -c "import secrets;print(secrets.token_urlsafe(64))"` |
| **PostgreSQL** | SQLite is dev-only. Set `RS_DATABASE_URL`, run `alembic upgrade head` |
| **S3-compatible storage** | The service refuses to start in production on filesystem storage — container disks are ephemeral and patient images would be lost on deploy |
| **Install Flutter** | The mobile app has never been compiled. `flutter analyze && flutter test` before trusting it |
| **Clinician review of the rules** | The risk thresholds and referral timeframes in **Admin → Configuration** are engineering defaults, not clinical ones |

---

## The honest limit

Even after all six steps you will have a model with **good held-out metrics** —
not a clinically validated device.

Clinical validation means prospective evaluation on a representative patient
population, conducted by qualified people, against a defined intended use, with
regulatory review appropriate to your jurisdiction. Held-out test accuracy is a
development signal.

This is why the system keeps a clinician in the loop on **every** screening, and
why the API refuses to accept a "validated" status without evidence. Leave the
model registered as `not_validated` until real validation exists.
