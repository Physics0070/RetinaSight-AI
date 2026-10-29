# Free-tier deployment

An all-free stack that does not expire. **Demo / synthetic data only** — free
tiers carry no uptime guarantee and no data-protection agreement, so do not
put real patient images through it.

| Piece | Service | Why it lasts |
|---|---|---|
| Dashboard | Cloudflare Pages | Static; never sleeps, no expiry |
| API | Hugging Face Spaces (Docker) | Sleeps only after ~48 h without traffic |
| Database | Neon Postgres | No expiry; suspends when idle, wakes in ~1 s |
| Images | Backblaze B2 (S3-compatible) | Free allowance, no expiry |
| Keep-warm | UptimeRobot / cron-job.org | Free ping so the Space never idles out |

Free-tier terms change. Check each provider's current limits before relying on
this. Create every account yourself and enter secrets only in each provider's
own settings page — **never in a chat, an issue, or a commit.**

## Order of operations

The services depend on each other's URLs, so do them in this order.

### 1. Database — Neon
1. Create a project and a database. Copy the **connection string**
   (`postgresql://…?sslmode=require`).
2. That string is `RS_DATABASE_URL`. The app rewrites `postgresql://` to the
   installed `psycopg` driver itself.

### 2. Image storage — Backblaze B2
1. Create a **private** bucket. Create an application key scoped to that bucket.
2. Note the bucket name, region, S3 endpoint, key ID and key.

### 3. API — Hugging Face Space
1. Create a Space, SDK **Docker**, blank template.
2. Build the bundle and push it to the Space's git repository:

   ```bash
   python scripts/package_hf_space.py
   cd build/hf-space
   git init && git add . && git commit -m "Deploy RetinaSight API"
   git remote add space https://huggingface.co/spaces/<you>/<space-name>
   git push space HEAD:main --force
   ```
   (`--force` only because the Space's initial commit is a placeholder README.)
3. In **Space → Settings → Variables and secrets**, add:

   | Name | Kind | Value |
   |---|---|---|
   | `RS_ENV` | variable | `production` |
   | `RS_DEBUG` | variable | `false` |
   | `RS_MODEL_PROVIDER` | variable | `onnx` |
   | `RS_ACTIVE_MODEL_VERSION` | variable | `dr-v2` |
   | `RS_STORAGE_PROVIDER` | variable | `s3` |
   | `RS_S3_BUCKET`, `RS_S3_REGION`, `RS_S3_ENDPOINT_URL` | variable | from step 2 |
   | `RS_PUBLIC_BASE_URL` | variable | the Space URL, `https://<you>-<space-name>.hf.space` |
   | `RS_CORS_ORIGINS` | variable | the Pages URL from step 4 (add after step 4) |
   | `RS_DATABASE_URL` | **secret** | from step 1 |
   | `RS_S3_ACCESS_KEY_ID`, `RS_S3_SECRET_ACCESS_KEY` | **secret** | from step 2 |
   | `RS_JWT_SECRET`, `RS_JWT_REFRESH_SECRET`, `RS_STORAGE_SIGNING_SECRET` | **secret** | three *different* random values (below) |
   | `RS_SEED_ADMIN_EMAIL` | variable | a real-looking address (reserved TLDs are rejected) |
   | `RS_SEED_ADMIN_PASSWORD` | **secret** | a strong password |

   Generate each random secret locally:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
   The service refuses to start in production on placeholder values or reused
   JWT secrets — that is intentional.
4. Check `https://<you>-<space-name>.hf.space/health/ready`.

### 4. Dashboard — Cloudflare Pages
1. Connect the GitHub repository.
2. Settings: **Root directory** `dashboard` · **Build command**
   `npm ci && npm run build` · **Output** `dist`.
3. Environment variable `VITE_API_BASE_URL` =
   `https://<you>-<space-name>.hf.space/api/v1`. The production build fails
   without it, by design.
4. `dashboard/public/_redirects` makes deep links (`/doctor/dashboard`) resolve
   to the app instead of a 404.
5. Put the resulting Pages URL into the Space's `RS_CORS_ORIGINS`, then restart
   the Space.

### 5. Keep the API warm
Add an HTTP monitor on `…/health/ready` every 5–10 minutes in UptimeRobot (or a
cron-job.org job). Open the link yourself shortly before any demo.

## Known limits

- First request after a long idle can take up to a minute while the Space wakes.
- A Space's disk is ephemeral. Nothing important lives there — the database is
  Neon and images are in B2 — but never configure local storage.
- Deploys are manual (push to the Space). Nothing rolls back automatically;
  `git revert` and push again.
