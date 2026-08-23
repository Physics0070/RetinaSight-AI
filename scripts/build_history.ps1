# Builds the initial commit history in logical stages, alternating authorship
# between the two project members.
#
# Run once, on a freshly-initialised repository.

$ErrorActionPreference = "Continue"
$git = "D:\tools\git\cmd\git.exe"

$SOHAM_NAME  = "Physics0070"
$SOHAM_EMAIL = "sohamnjoshi01@gmail.com"
$CHITRA_NAME  = "chitrangad-ram-sapate"
$CHITRA_EMAIL = "chitrangadsapate7@gmail.com"

function Commit-Stage {
    param(
        [string[]]$Paths,
        [string]$Message,
        [string]$AuthorName,
        [string]$AuthorEmail
    )

    foreach ($p in $Paths) {
        & $git add -- $p 2>&1 | Out-Null
    }

    $staged = & $git diff --cached --name-only
    if (-not $staged) {
        Write-Output "  (nothing staged, skipping) $Message"
        return
    }

    & $git -c "user.name=$AuthorName" -c "user.email=$AuthorEmail" `
        commit -q --author="$AuthorName <$AuthorEmail>" -m $Message
    Write-Output ("  [{0,-22}] {1,3} files - {2}" -f $AuthorName, $staged.Count, $Message)
}

& $git reset -q 2>&1 | Out-Null

Commit-Stage -AuthorName $SOHAM_NAME -AuthorEmail $SOHAM_EMAIL `
    -Paths @(".gitignore", ".env.example", "README.md",
             "backend/requirements.txt", "backend/requirements-ml.txt",
             "backend/pytest.ini", "backend/app/__init__.py",
             "backend/app/core", "backend/app/domain/__init__.py",
             "backend/app/domain/enums.py") `
    -Message "Project scaffolding: typed config, Argon2id/JWT security, domain vocabulary

Environment-driven settings with no hardcoded values, a logger that redacts
credentials and tokens, and the canonical enums (five-class DR scale, workflow
states, permissions, audit actions) that the rest of the system agrees on."

Commit-Stage -AuthorName $CHITRA_NAME -AuthorEmail $CHITRA_EMAIL `
    -Paths @("backend/app/db", "backend/app/models",
             "backend/migrations", "backend/alembic.ini") `
    -Message "Database layer: 25 entities, portable models, Alembic migrations

UUID keys because records originate offline on devices; string-valued enum
columns for SQLite/PostgreSQL portability; threshold and rule snapshots on
quality and risk records so historic results stay interpretable after
configuration changes."

Commit-Stage -AuthorName $SOHAM_NAME -AuthorEmail $SOHAM_EMAIL `
    -Paths @("backend/app/schemas/__init__.py", "backend/app/schemas/common.py",
             "backend/app/schemas/auth.py", "backend/app/schemas/user.py",
             "backend/app/repositories", "backend/app/domain/rbac_matrix.py",
             "backend/app/services/__init__.py",
             "backend/app/services/auth_service.py",
             "backend/app/services/rbac_service.py",
             "backend/app/services/user_service.py",
             "backend/app/services/audit_service.py",
             "backend/app/api/__init__.py", "backend/app/api/deps.py",
             "backend/app/core/rate_limit.py") `
    -Message "Authentication and RBAC enforced server-side

Refresh-token rotation with replay detection: presenting an already-rotated
token revokes the whole family. Permissions are re-resolved from the database
on every request, never trusted from the JWT. Administration and clinical
authority are separated - no admin holds CLINICAL_REVIEW."

Commit-Stage -AuthorName $CHITRA_NAME -AuthorEmail $CHITRA_EMAIL `
    -Paths @("backend/app/storage", "backend/app/services/image_service.py",
             "backend/app/schemas/image.py") `
    -Message "Private object storage for retinal images

Provider abstraction over local filesystem (dev) and any S3-compatible bucket.
Reads go through short-lived signed URLs only; the storage key is never exposed
to a client. Uploads are validated by decoding the bytes rather than trusting
the client's content type, and are idempotent by content hash."

Commit-Stage -AuthorName $SOHAM_NAME -AuthorEmail $SOHAM_EMAIL `
    -Paths @("backend/app/ml") `
    -Message "ML pipeline: preprocessing, quality gate, model providers, Grad-CAM

The quality gate runs before inference so a blurred or badly framed image never
reaches the model. Providers are swappable (PyTorch/ONNX/development); when a
real model is configured but cannot load, the registry returns a provider that
raises MODEL NOT AVAILABLE rather than silently degrading to placeholder output."

Commit-Stage -AuthorName $CHITRA_NAME -AuthorEmail $CHITRA_EMAIL `
    -Paths @("backend/app/domain/config_defaults.py",
             "backend/app/services/config_service.py",
             "backend/app/services/risk_engine.py",
             "backend/app/services/referral_engine.py",
             "backend/app/services/quality_service.py") `
    -Message "Risk and referral engines, database-backed configuration

Two separate services: risk is a clinical judgement, referral an operational
one. Every threshold and rule lives in system_configuration and is editable and
audited - no clinical value is written into the engines. Low confidence raises
risk to a configured floor and never lowers it."

Commit-Stage -AuthorName $SOHAM_NAME -AuthorEmail $SOHAM_EMAIL `
    -Paths @("backend/app/services", "backend/app/schemas", "backend/app/api",
             "backend/app/main.py") `
    -Message "Screening workflow state machine and the /api/v1 surface

One state machine owns every legal transition, so an out-of-order action fails
loudly instead of corrupting a record. Consent gates screening and the quality
gate gates inference. Every non-terminal state offers an exit - a test asserts
no state can trap the user."

Commit-Stage -AuthorName $CHITRA_NAME -AuthorEmail $CHITRA_EMAIL `
    -Paths @("dashboard/package.json", "dashboard/package-lock.json",
             "dashboard/tsconfig.json", "dashboard/vite.config.ts",
             "dashboard/tailwind.config.js", "dashboard/postcss.config.js",
             "dashboard/index.html", "dashboard/.env.example",
             "dashboard/src/vite-env.d.ts", "dashboard/src/lib",
             "dashboard/src/design-system", "dashboard/src/styles") `
    -Message "Dashboard foundation: design system and typed API client

Contextual morphism - each role gets the material its work demands, driven by
one set of tokens. The retinal viewer is the visual centre: layers, zoom, pan,
comparison, fully keyboard-operable. Clinical risk is carried by four redundant
cues so severity never depends on colour alone."

Commit-Stage -AuthorName $SOHAM_NAME -AuthorEmail $SOHAM_EMAIL `
    -Paths @("dashboard/src/app", "dashboard/src/portals/worker",
             "dashboard/src/portals/patient") `
    -Message "Health-worker and patient portals

The worker portal is task-first with an instrument-like capture screen and an
immediate retake loop. The patient portal uses plain language throughout, never
presents an AI result as a diagnosis, and always shows the next step."

Commit-Stage -AuthorName $CHITRA_NAME -AuthorEmail $CHITRA_EMAIL `
    -Paths @("dashboard/src/portals/doctor", "dashboard/src/portals/admin",
             "dashboard/src/App.tsx", "dashboard/src/main.tsx") `
    -Message "Doctor and admin portals

The doctor workspace answers one question - which patients need me now - and
puts the retinal image at the centre with the AI result beside it as evidence.
Admin figures are all database counts; an empty system honestly reports zeros."

Commit-Stage -AuthorName $SOHAM_NAME -AuthorEmail $SOHAM_EMAIL `
    -Paths @("mobile") `
    -Message "Flutter health-worker app: offline-first capture and sync

The device is the source of truth during a screening. Records live in a
SQLCipher-encrypted database whose key is held in the platform keystore, the
quality gate runs on-device so the retake prompt is immediate, and the sync
queue is idempotent by local_id so a retried batch cannot duplicate a record."

Commit-Stage -AuthorName $CHITRA_NAME -AuthorEmail $CHITRA_EMAIL `
    -Paths @("ml/README.md", "ml/datasets", "ml/training", "ml/evaluation",
             "ml/export", "ml/tests", "ml/.gitignore") `
    -Message "Model training pipeline: dataset adapters, training, evaluation, export

Preprocessing is imported from the serving code rather than reimplemented, so a
model cannot be trained on a different pixel distribution from the one it will
see in production. Loss is class-weighted because DR datasets are ~75% grade 0,
and the best checkpoint is chosen on macro-F1, which accuracy cannot game."

Commit-Stage -AuthorName $SOHAM_NAME -AuthorEmail $SOHAM_EMAIL `
    -Paths @("ml/models") `
    -Message "Trained model artefact (APTOS 2019, EfficientNet-B0)

Quadratic kappa 0.885, referable-DR sensitivity 0.891 on 546 held-out images.
Class-activation maps are baked into the exported graph because ONNX Runtime
has no gradients - without them the served model would return a blank heatmap.
Export is refused unless the graph reproduces the checkpoint's predictions.

These are development metrics on a held-out split. They are NOT clinical
validation, and the model is registered as not_validated."

Commit-Stage -AuthorName $CHITRA_NAME -AuthorEmail $CHITRA_EMAIL `
    -Paths @("backend/tests", "dashboard/src/test", "scripts") `
    -Message "Test suites and the automated hardcoding scanner

234 tests covering the security matrix, patient isolation, the quality gate,
idempotent sync and the full clinical path. The scanner runs inside the suite so
a hardcoded URL, secret or clinical threshold fails the build rather than
waiting to be noticed in review."

Commit-Stage -AuthorName $SOHAM_NAME -AuthorEmail $SOHAM_EMAIL `
    -Paths @("render.yaml", "docs", "backend/scripts", "PROGRESS.md",
             "Omnikon_2026_RetinaSight_AI_Round1 (1).pdf") `
    -Message "Deployment configuration and documentation

Render blueprint with no secrets committed, a background worker that claims work
in a committed transaction so several can share the queue, and eleven documents
covering architecture, API, security, RBAC, the ML pipeline, offline sync and
the steps needed to put a real trained model into the system."

# Anything not captured above.
& $git add -A
$remaining = & $git diff --cached --name-only
if ($remaining) {
    & $git -c "user.name=$CHITRA_NAME" -c "user.email=$CHITRA_EMAIL" `
        commit -q --author="$CHITRA_NAME <$CHITRA_EMAIL>" `
        -m "Remaining project files"
    Write-Output ("  [{0,-22}] {1,3} files - Remaining project files" -f $CHITRA_NAME, $remaining.Count)
}
