# Document & Workflow Automation Platform

AI-powered platform for document processing, invoice handling, vendor management, workflow automation, and local AI assistants.

## Overview

DocFlow is a local-first FastAPI + React application that covers document intake through human review:

Upload → OCR/process → classify → extract (invoice/PO/GRN) → validate / 3-way match → review → analytics / AI assistants

## Technology stack

| Layer | Stack |
| --- | --- |
| Frontend | React 18, Vite, React Router |
| Backend | FastAPI, SQLAlchemy, Alembic, Pydantic |
| Database | PostgreSQL (+ pgvector for RAG) |
| Workers | FastAPI BackgroundTasks (local) or Redis + Celery |
| Email | Provider-neutral IMAP (optional; mock for tests) |
| Auth | Local JWT + RBAC (admin / reviewer / operator / viewer) |
| ML (local) | TF-IDF classification, IsolationForest anomalies, sentence-transformers RAG |

## Project Structure

```
├── frontend/              # React (Vite) application
├── backend/               # FastAPI application
├── docker-compose.yml     # Production-like local stack (Step 25)
├── .env.example           # Compose variable substitution template
├── .env.docker.example    # Backend container env template
├── .gitignore
└── README.md
```

## Prerequisites

**Local development**

- Node.js 18+
- Python 3.11+
- PostgreSQL 14+
- Tesseract OCR (for image and scanned PDF processing)

**Docker (optional)**

- Docker Engine + Docker Compose v2

---

## Development setup (non-Docker)

### Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # macOS / Linux

# Edit .env: DATABASE_URL must use host localhost (not the Docker hostname postgres)
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health
- Readiness: http://localhost:8000/api/v1/health/ready

Set `AUTH_BOOTSTRAP_ADMIN_PASSWORD` in `.env` once to create the first admin when the users table is empty.

See `backend/README.md` for Tesseract and API details.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173 (or the port Vite prints; `vite.config.js` may use 5174).

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`. Optional `VITE_API_BASE_URL` is documented in `frontend/.env.example` (leave empty for same-origin proxy).

---

## Docker setup (production-like local stack)

This is a **reproducible production-like environment**, not a claim that the app is fully production-hardened.

Services: `frontend`, `backend`, `postgres`, `redis`, `worker` (Celery), `beat` (Celery Beat).

### 1. Configure secrets

```bash
copy .env.example .env
copy .env.docker.example .env.docker
```

Edit both files:

| Variable | Purpose |
| --- | --- |
| `POSTGRES_PASSWORD` | Database password (must match in `.env` and `.env.docker` usage) |
| `AUTH_JWT_SECRET` | Strong random secret (≥ 32 chars); required when `APP_ENV=production` |
| `AUTH_BOOTSTRAP_ADMIN_PASSWORD` | Creates first admin if users table is empty |
| `CORS_ORIGINS` | Explicit frontend origins (no `*`) |

Never commit `.env` or `.env.docker`.

### 2. Build and start

```bash
docker compose build
docker compose up
```

### 3. Ports and services

| Service | Host access | Notes |
| --- | --- | --- |
| frontend (nginx) | http://localhost:5173 | SPA + reverse proxy `/api` → backend |
| backend (uvicorn) | http://localhost:8000 | Also reachable via frontend `/api` |
| postgres | *not published* | Hostname `postgres` |
| redis | *not published* | Hostname `redis` |
| worker | none | Celery worker (`PROCESSING_WORKER_MODE=celery`) |
| beat | none | Celery Beat (email poll schedule when provider enabled) |

### 4. Migrations

On backend container start, `docker-entrypoint.sh` runs:

```bash
alembic upgrade head
```

once, then starts a **single** uvicorn worker (avoids concurrent migration races). Latest migration revision: `20260324_0021`.

Manual migration (if needed):

```bash
docker compose exec backend alembic upgrade head
```

### 5. Storage persistence

Named volumes:

- `postgres_data` — PostgreSQL data
- `document_uploads` — `backend/storage/uploads`
- `anomaly_models` / `classification_models` — local ML artifacts

Uploads survive `docker compose restart`. They are removed only if you delete the volumes (`docker compose down -v`).

### 6. Smoke checks

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/health/ready

curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"YOUR_BOOTSTRAP_PASSWORD\"}"
```

Open http://localhost:5173 and sign in. Prefer same-origin API via the frontend (`/api/...`).

### 7. Stop / restart

```bash
docker compose stop
docker compose start
docker compose down          # keep volumes
docker compose down -v       # DESTROYS database + uploads
```

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Backend exits on start | Weak/missing `AUTH_JWT_SECRET` with `APP_ENV=production` |
| Readiness 503 | Postgres not healthy yet; wait or check `docker compose logs postgres` |
| Login fails | Bootstrap password not set, or admin already created with another password |
| Frontend blank API errors | Backend unhealthy; check `docker compose logs backend` |
| Permission errors on uploads | Entrypoint should chown volumes; recreate containers if customized |

---

## Environment modes

| `APP_ENV` | Behavior |
| --- | --- |
| `development` | Docs on by default; reload OK for local uvicorn; insecure JWT default tolerated |
| `production` | DEBUG forced off; docs off unless `ENABLE_DOCS=true`; JWT/CORS validated at startup; no reload in Docker |

`DATABASE_URL` switches host via env only:

- Local: `@localhost:5432`
- Docker: `@postgres:5432`

---

## Current Scope

Includes Steps 1–28 (submission-ready UI + API wiring):

- Document upload, OCR/text extraction, classification, invoice/PO/GRN extraction
- Background document processing jobs (local FastAPI BackgroundTasks; sync mode for tests)
- Local JWT authentication and role-based access control (admin / reviewer / operator / viewer)
- Batch document ingestion and provider-independent email-attachment ingestion (IMAP optional; no OAuth Gmail/Outlook APIs)
- Controlled agentic automation with deterministic planning and an explicit read-only tool registry (no arbitrary code, shell, or destructive actions)
- Advanced analytics / KPI dashboard and management reporting (read-only; multi-currency totals kept separate)
- Vendors, invoice↔PO validation, human review queue
- Document relationships with human-confirmed links and PO/GRN suggestions
- Deterministic 3-way matching (Invoice ↔ PO ↔ GRN) with explainable matched/mismatch/needs_review results, including line-item quantity matching when extractable (assistive only)
- Local RAG knowledge assistant, read-only SQL agent, investigation agent
- Allowlisted workflow engine and local ML anomaly detection (IsolationForest)
- Multi-level duplicate detection (exact SHA-256, business invoice match, similarity) with human confirm/dismiss only
- Field intelligence for stored invoice, purchase order, and goods receipt fields
- ML-assisted document classification (TF-IDF + LogisticRegression) with rule-based fallback
- **Docker Compose production-like stack**, health/readiness probes, configurable CORS, structured logging, persistent upload volumes (Step 25)
- **Production security hardening** (Step 26): security headers, in-process rate limits, login cooldown, password strength, safer uploads, SQL/agent/RAG regression guards, request IDs, audit scrubbing, useful DB indexes
- **Redis + Celery workers** and provider-neutral **IMAP email ingestion** with polling (Step 27); local BackgroundTasks remain the default without Redis
- **Submission UI completion** (Step 28): all primary nav pages connected (Dashboard KPIs, Invoices, Purchase Orders, Audit Logs); no “Coming soon” for implemented modules

---

## Tests

**Local development (default)**

```env
PROCESSING_WORKER_MODE=local
EMAIL_PROVIDER=none
```

Document processing uses FastAPI BackgroundTasks (or sync when `DOCUMENT_PROCESSING_SYNC=true` in tests).

**Celery mode**

```env
PROCESSING_WORKER_MODE=celery
REDIS_URL=redis://localhost:6379/0
```

```bash
# terminal A
celery -A app.workers.celery_app.celery_app worker --loglevel=info

# terminal B (optional email schedule)
celery -A app.workers.celery_app.celery_app beat --loglevel=info
```

**IMAP email**

```env
EMAIL_PROVIDER=imap
EMAIL_IMAP_HOST=imap.example.com
EMAIL_IMAP_PORT=993
EMAIL_IMAP_USERNAME=...
EMAIL_IMAP_PASSWORD=...
EMAIL_IMAP_FOLDER=INBOX
EMAIL_IMAP_USE_SSL=true
EMAIL_POLL_INTERVAL_SECONDS=300
```

- IMAP is provider-neutral (Gmail/Outlook may work via IMAP depending on account settings).
- OAuth Gmail/Outlook APIs are **not** implemented.
- Credentials must stay in env/secrets managers — never in logs or API responses.
- Manual poll: `POST /api/v1/ingestion/email/poll` (operator+); status: `GET /api/v1/ingestion/email/status`.

---

## Security notes (Step 26)

In-process rate limiting and login lockout suit the **default single-instance** local deployment. When running multiple API replicas, prefer a shared limiter store (e.g. Redis) in a later hardening pass.

## Future cloud deployment

Docker Compose is a foundation only. Real production still needs, among other things:

- HTTPS/TLS termination
- Managed PostgreSQL
- Object storage (S3-compatible) instead of local disk
- Redis/Celery (or equivalent) for distributed workers
- Reverse proxy / load balancer
- Secrets manager
- Rate limiting, monitoring, centralized logs
- Backups and disaster recovery
- Autoscaling and vulnerability scanning

Possible future hosts: AWS, Azure, GCP, Railway, Render. **Do not treat “Docker works locally” as production-ready.**

---

## Tests

```bash
cd backend
.venv\Scripts\activate   # Windows
pytest                   # Step 28: 326 passed

cd ../frontend
npm run build            # Vite production build
```

Optional live API smoke (with backend running): health, readiness, login, documents, invoices, vendors, purchase orders, validation, reviews, analytics, RAG, SQL, investigation, controlled agent, workflows, ingestion, email status, audit logs.
