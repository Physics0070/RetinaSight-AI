# RetinaSight AI — final tasks checklist

Live status for the three requested tasks. Updated as work lands.

Legend: `[x]` done and verified · `[~]` in progress · `[ ]` not started · `[!]` blocked or honest-negative result

---

## Task 1 — Change the colour scheme  ✅ COMPLETE

- [x] New palette designed: **spectral accents on neutral graphite**
- [x] Ground de-tinted from navy to neutral — a tinted surround shifts the apparent
      colour of the fundus image, and hue is part of the clinical judgement
- [x] Role accents moved off the severity hues (old worker accent was **3°** of hue
      from the low-risk colour; old patient accent **3°** from high-risk)
- [x] Severity scale deliberately **unchanged** — those associations are learned and
      clinically load-bearing
- [x] All four portals verified visually distinct in the browser
- [x] Contrast suite rewritten to **parse `tokens.css`** instead of keeping a
      hand-copied palette that could silently drift
- [x] New test pins accent-vs-severity hue separation (≥35°, actual min 39°)
- [x] Dashboard tests **74 → 87**, all green; production build clean
- [x] Fixed a bug found while verifying: `transition: background` on `body` latched
      the old value forever when the role changed, so **every portal was painting on
      the `:root` ground** — the per-role grounds were written but never shipped

Commit `356af93`.

| Role | Ground | Accent |
|---|---|---|
| worker | `#0a0c0a` | lime `#a3e635` |
| doctor | `#070709` | periwinkle `#7aa2ff` |
| patient | `#121116` | lilac `#c9b6f7` |
| admin | `#0c0a11` | orchid `#e879f9` |

---

## Task 2 — Total accuracy over 90%  ❗ MEASURED — TARGET NOT REACHED

**Result: 5-class accuracy peaks at 0.8700. The >90% target was not met, and I
could not meet it honestly.**

Measured on the 546-image held-out split (`split_seed=42`), two members that
genuinely share that split. Full grid in `ml/models/ensemble-2member.json`.

| Configuration | rule | **acc** | kappa | macro-F1 | ref. sens |
|---|---|---|---|---|---|
| member1 (seed 42), no TTA | expected-grade | 0.8150 | 0.9203 | 0.6687 | 0.9502 |
| member1 (seed 42), no TTA | argmax | 0.8388 | 0.9037 | 0.6995 | 0.9412 |
| member1 + TTA | argmax | 0.8480 | 0.9092 | 0.7147 | 0.9412 |
| member2 (seed 143), no TTA | expected-grade | 0.8242 | 0.9252 | 0.6994 | 0.9412 |
| member2 (seed 143), no TTA | argmax | 0.8535 | 0.9151 | 0.7335 | 0.9231 |
| **member2 + TTA** | **argmax** | **0.8700** | 0.9266 | 0.7513 | 0.9231 |
| Ensemble, no TTA | argmax | 0.8571 | **0.9274** | 0.7346 | 0.9321 |
| Ensemble + TTA | expected-grade | 0.8425 | 0.9258 | 0.7162 | **0.9593** |
| Ensemble + TTA | argmax | 0.8590 | 0.9205 | 0.7351 | 0.9231 |

### What the grid actually shows

- **TTA works, modestly.** +0.0092 on member1 and +0.0165 on member2 (argmax).
  Same direction on both, so it is a real effect rather than split noise.
- **The ensemble did *not* help accuracy.** Two members averaged (0.8590) score
  *below* the better member alone with TTA (0.8700), because member1 is the
  weaker model and drags the mean down. Ensembling did produce the best kappa
  (0.9274), which is the metric it is expected to help.
- **argmax beats expected-grade on accuracy every time** (+2 to +5 points) and
  **loses referable sensitivity every time**. That is the ordinal objective
  working as designed, not a bug — it buys smaller-distance errors with
  exact-match accuracy.
- **0.8700 is an upper bound, not an expectation.** It is the maximum over 12
  configurations scored on the same 546 images; picking the winner post-hoc on
  one split is itself a mild form of overfitting. The script now prints this
  caveat next to the figure so it cannot be quoted bare.

### Why I am not claiming >90%

Published state of the art on APTOS 5-class is roughly 85–88%. Reaching 90%
here would have required one of three things, all of which I refused:
testing on training data, redefining "accuracy" as the binary referable
decision (~95%), or reporting the best seed as typical.

**Metrics that genuinely do exceed 90%,** reported as what they are:

| Metric | Value | What it means |
|---|---|---|
| Quadratic weighted kappa | **0.9274** | agreement on the ordinal grade — the standard DR metric |
| Referable-DR sensitivity | **0.9593** | catches 95.9% of moderate-or-worse cases |

For a screening tool that refers rather than diagnoses, referable sensitivity is
the number that matters clinically. It is not the same thing as accuracy and is
not offered as a substitute.

### Still running
A third member (seed 244) is training and will be added; it may move the
ensemble figures slightly but will not close a 3-point gap.

---

## Task 2 — working notes

**Honest position stated up front:** the target is 5-class exact-match accuracy on a
held-out split. Current is **0.835**. Published state of the art on this dataset is
roughly 85–88%. I do not expect ensemble + TTA to reach 90%, and I will not reach it
by testing on training data, by relabelling the binary referable decision as
"accuracy", or by reporting the best seed as typical.

Metrics that **already exceed 90%** and will be reported as what they are — not
substituted for accuracy:
- quadratic weighted kappa **0.9271 ± 0.0062**
- referable-DR sensitivity **0.9412 ± 0.0240**

### Blocking defect found and fixed first
- [x] `train.py` used one seed for **both** weight init and the train/val split, so
      the three existing runs had three different held-out sets
- [x] Confirmed severity: of seed 143's 546 validation images, **85% sit in seed 42's
      training set**; only **15 images** were held out by all three runs
- [x] → averaging those checkpoints would have been **leakage**, producing a high
      number that meant nothing
- [x] `split_seed` separated from `seed`; new `--split-seed` flag (commit `6f5cbf1`)
- [x] `evaluate.py` hardcoded argmax, so it misreported every ordinal checkpoint —
      disagreeing with that run's own `metrics.json` for identical weights. This was
      the same bug in a third place (also present in the ONNX serving path).

### Remaining
- [~] Train 2 fresh members on the fixed split (`--split-seed 42`, seeds 143 / 244)
      — **run 1 in progress**, epoch 18/30, kappa 0.9252. ~2.25 min/epoch, so
      roughly 2¼ hours for both, sequential on a 6 GB GPU
- [x] Build `ml/evaluation/ensemble.py`, which measures each member alone, then with
      TTA, then combined — so the TTA gain and the ensemble gain are attributable
      separately instead of reported as one blended number
- [x] **Leakage guard verified**: the tool refuses to average the three old
      checkpoints and names their three different splits. Without it the naive
      ensemble would have produced an inflated number that meant nothing
- [ ] Measure TTA alone, then the ensemble, on the common held-out split
- [ ] Report under **both** decision rules — the ordinal rule trades exact-match
      accuracy away to buy referable sensitivity:

      | rule | accuracy | kappa | referable sens |
      |---|---|---|---|
      | expected-grade | 0.8333 | 0.9324 | 0.9140 |
      | argmax | 0.8388 | 0.9275 | 0.8914 |

- [ ] Verify whatever ships by replaying the held-out split **through the backend's
      own ONNX provider**, not the torch model, and diffing against `metrics.json`

---

## Task 3 — Nothing hardcoded  ✅ COMPLETE

Starting point: scanner passed over 206 files, but on **9 blanket file exemptions**,
each suppressing every rule for that path. That is a hole, not a policy — an
allowlisted file could have held an AWS key, a private key or a Firebase import and
the scan would still have printed `PASS`. **4 of the 9 turned out to suppress rules
that never fired at all.**

Values were **removed**, not excused:

- [x] `.env.example` is now the single source of development defaults. The backend
      reads it at *lowest* precedence outside production; Vite does the same for the
      dashboard. A fresh clone still runs with no setup, while no host, URL or secret
      is compiled into source
- [x] Every environment-specific field declares an **empty** default. Only genuine
      protocol constants keep a literal — an API prefix and a JWT algorithm are
      neither secret nor environment-specific
- [x] **Production refuses to start** on any value that is unset, matches a
      placeholder marker, or still equals the value published in `.env.example`.
      That last check matters: the localhost CORS origins carry no marker and look
      like ordinary settings, so the first two checks miss them. It is also
      order-independent, unlike the env-file choice, which is fixed when the class
      is defined
- [x] Reusing one secret for both token families is rejected — that lets a stolen
      access token be replayed as a refresh token
- [x] Dashboard now fails the **build** when `VITE_API_BASE_URL` is missing, instead
      of shipping a bundle that throws in the user's browser. Verified both ways
- [x] Mobile config dropped its `defaultValue` entirely — `String.fromEnvironment`
      resolves at compile time, so a default there ships inside any APK built without
      the define, silently pointing at whoever built it
- [x] `scripts/seed_demo.py` generates its demo password instead of carrying one. A
      working credential in a public repo is a working credential however it is
      labelled, and that script seeds accounts with real clinical permissions
- [x] Exemptions are now **5 narrow `(path, rule)` pairs**, each excusing only the
      rule it needs; every other rule still applies to those paths
- [x] Untracked `dashboard/tsconfig.tsbuildinfo`, added `*.tsbuildinfo` to gitignore
- [x] `.env` files are now scanned at all — they carry no scannable suffix but are
      exactly where a real secret gets pasted by accident

### Three new tests hold the line
- exemptions must be a **strict subset** of the rules (no blanket entries)
- `.env` files must actually be scanned
- a credential planted inside `tests/` must still be caught — **it is, and would not
  have been before**

Backend **147 → 150** tests. Scanner PASS across **211** files with 5 exemptions.
Commit `55e22da`.

### Irreducible by nature (remain, each with a written reason)
- `scripts/check_no_hardcoding.py` → `firebase` only — the scanner must contain the
  patterns it searches for
- `.env.example`, `dashboard/.env.example` → `localhost_url` only — they *are* the
  development defaults, and production never reads them
- `backend/tests/test_no_hardcoding.py` → `firebase`, and
  `backend/tests/test_config_paths.py` → `postgres_dsn` — exempted per file rather
  than by weakening the whole `tests/` directory

---

## Cross-cutting state

- [x] Backend **147** tests · ML **35** · Dashboard **87** · Mobile **26**
- [x] Scanner PASS across 206 files
- [x] `dr-v2` serving at 456×456 with real Grad-CAM and the decision rule baked into
      the graph; registry `not_validated`, which is honest — no clinical validation
      has been performed
- [ ] Flutter app has never been run on a real device or emulator
- [ ] Backend suite has only ever run against SQLite, never PostgreSQL
- [ ] **Kaggle API token was pasted into a chat and must be rotated**
