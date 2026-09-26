# Document & Workflow Automation — Backend

FastAPI service for the Document & Workflow Automation Platform.

## Setup

1. Create and activate a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
```

2. Install Python dependencies:

```bash
pip install -r requirements.txt
```

3. Install Tesseract OCR (required for image/scanned PDF processing):

### Windows

1. Download the installer from:
   https://github.com/UB-Mannheim/tesseract/wiki
2. Run the installer (default location is usually `C:\Program Files\Tesseract-OCR`).
3. During setup, include English language data.
4. Either add the install folder to your system PATH, or set `TESSERACT_CMD` in `.env`:

```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Verify from PowerShell:

```powershell
tesseract --version
```

### macOS

```bash
brew install tesseract
```

### Linux (Debian/Ubuntu)

```bash
sudo apt-get install tesseract-ocr
```

4. Configure environment:

```bash
copy .env.example .env          # Windows
cp .env.example .env            # macOS / Linux
```

Edit `.env` with your PostgreSQL connection details and optional `TESSERACT_CMD`.

5. Ensure PostgreSQL is running and the database named in `DATABASE_URL` exists.

6. Run migrations:

```bash
alembic upgrade head
```

7. Start the API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Endpoints

| Method | Path                              | Description                 |
|--------|-----------------------------------|-----------------------------|
| GET    | `/api/v1/health`                  | Service health check        |
| POST   | `/api/v1/documents`               | Upload a document           |
| GET    | `/api/v1/documents`               | List documents (paged)      |
| GET    | `/api/v1/documents/{id}`          | Get document metadata       |
| DELETE | `/api/v1/documents/{id}`          | Delete document and file    |
| POST   | `/api/v1/documents/{id}/process`         | Extract text / run OCR + classify |
| GET    | `/api/v1/documents/{id}/text`            | Get extracted text                |
| POST   | `/api/v1/documents/{id}/classify`        | Re-run document classification    |
| GET    | `/api/v1/documents/{id}/classification`  | Get classification result         |
| POST   | `/api/v1/classification/train`           | Train local ML classifier (dev)   |
| GET    | `/api/v1/classification/model-status`    | ML classifier availability        |
| POST   | `/api/v1/documents/{id}/extract`         | Extract invoice fields            |
| GET    | `/api/v1/documents/{id}/invoice`         | Get saved invoice data            |
| POST   | `/api/v1/documents/{id}/extract-po`      | Extract purchase order fields     |
| GET    | `/api/v1/documents/{id}/purchase-order`  | Get saved purchase order data     |
| GET    | `/api/v1/documents/{id}/field-intelligence` | Field checks for invoice/PO data |
| GET    | `/api/v1/validations`                    | List validations                  |
| GET    | `/api/v1/validations/{id}`               | Get one validation                |
| POST   | `/api/v1/validations/invoice/{invoice_id}/purchase-order/{purchase_order_id}` | Validate invoice vs PO |

Interactive docs: http://localhost:8000/docs

Uploaded files are stored under `storage/uploads/` (configurable via `UPLOAD_DIR`).

Text extraction supports PDF (selectable text + OCR fallback) and PNG/JPG/JPEG. DOCX/XLSX/CSV remain upload-only in this step.

Classification uses a local hybrid of rule/pattern scoring plus an optional TF-IDF + LogisticRegression model. Categories: invoice, purchase_order, contract, receipt, bank_statement, other. If no ML model is trained, behavior falls back to the existing rule-based classifier.

Invoice and purchase-order field extraction use local regex/pattern parsing only (no paid or LLM APIs).

Invoice vs PO validation compares vendor, currency, subtotal, tax, and total with a small configurable amount tolerance.

## ML Document Classification (Step 17)

Local, deterministic classifier using scikit-learn:

- Features: TF-IDF word/bigram vectors
- Model: LogisticRegression (`random_state=42`)
- Local synthetic training dataset: `app/data/classification/starter_training_set.json`
  (~105 demo examples, ~15 per label across invoice, purchase_order, goods_receipt, contract, receipt, bank_statement, other)
- Stratified train/test split (`test_size=0.25`, `random_state=42`) so evaluation is not run on training text
- Holdout evaluation reports accuracy, macro precision/recall/F1, per-class metrics, and a confusion matrix
- **Warning:** evaluation metrics are measured on this local synthetic holdout set only and are **not** production accuracy
- Model artifact: `storage/models/document_classifier.joblib` (gitignored); version `1.2.0`

Train locally (no auth/RBAC in this project yet):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/classification/train
```

The train response includes holdout `evaluation` metrics. `GET /api/v1/classification/model-status` returns `evaluation_accuracy` / `evaluation_macro_f1` when a trained model with evaluation metadata exists.

Decision policy:

1. Always run the rule-based classifier.
2. If a trained model exists, run ML prediction.
3. Agreement → average confidences + 0.05 boost (`hybrid_agree`).
4. Disagreement with a clearly stronger side (≥0.70 and margin ≥0.15) → prefer stronger × 0.85 (`hybrid_prefer_stronger`).
5. Otherwise → `other` with capped low confidence (`hybrid_uncertain`).
6. If ML is unavailable → rule-based only.

`document_type` / `classification_confidence` remain the final values used by extraction and review. Additional evidence fields store rule/ML predictions and method. Disagreement can open a `classification_model_disagreement` review without auto-approving or deleting documents.

## Document Relationships & 3-Way Matching (Step 18)

### Part 1 — Goods Receipt & relationships
- New document type: `goods_receipt` (Goods Receipt / GRN)
- Local deterministic GRN extraction (GRN number, date, vendor, PO number, quantity received)
- Explicit document relationships (human-confirmed only):
  - `invoice_purchase_order`
  - `goods_receipt_purchase_order`
  - `invoice_goods_receipt`
- Relationship suggestions match PO / GRN numbers from extracted fields or invoice text
- Suggestions are **not** auto-created; confirm in the Documents → Relationships UI

### Part 2 — Deterministic 3-way matching
Compare Invoice ↔ Purchase Order ↔ Goods Receipt across:

| Dimension | Behavior |
|---|---|
| Vendor | Normalized vendor names across all three |
| PO reference | Invoice PO text + PO number + GRN PO number |
| GRN reference | Invoice GRN text vs GRN number (missing invoice GRN → needs_review, not mismatch) |
| Quantity | `not_evaluable` until line-item quantities exist |
| Financial | Reuses existing Invoice ↔ PO validation (subtotal/tax/total/currency) |
| Relationships | Required Part 1 relationship links must be present |

Statuses: `matched` | `mismatch` | `needs_review`  
Precedence: any contradiction → mismatch; missing/incomplete evidence → needs_review; otherwise matched (quantity may remain not_evaluable).

Reviews:
- `three_way_match_mismatch` / `three_way_match_needs_review` on the invoice document
- Matched results do not create a review
- Existing review deduplication applies

```bash
curl -X POST http://127.0.0.1:8000/api/v1/validations/three-way \
  -H "Content-Type: application/json" \
  -d "{\"invoice_document_id\":\"...\",\"purchase_order_document_id\":\"...\",\"goods_receipt_document_id\":\"...\"}"
```

**Limitations:** This is assistive validation only — it does not approve invoices, block payments, or automate procurement. Advanced OCR table recognition is not implemented; line items are parsed from normalized text patterns only.

### Line items & quantity matching (Step 19)

- Reusable `document_line_items` rows for invoice / purchase_order / goods_receipt
- Quantity semantics: PO=`ordered`, GRN=`received`, Invoice=`invoiced`
- Deterministic matching: SKU → exact description → unambiguous token equality
- Quantity rule (within `QUANTITY_MATCH_TOLERANCE`, default `0.01`):
  - PO ordered ≥ GRN received
  - GRN received ≥ Invoice invoiced
- Missing/ambiguous line links → quantity `needs_review`
- No line items → quantity `not_evaluable` (blocks overall `matched`)

```bash
curl http://127.0.0.1:8000/api/v1/documents/{document_id}/line-items
curl -X POST http://127.0.0.1:8000/api/v1/documents/{document_id}/extract-line-items
```

### Background processing jobs (Step 20)

Document processing runs through a persistent job record so work is not tied only to the HTTP request lifecycle.

- Job type: `document_processing`
- Statuses: `queued` → `running` → `completed` | `failed` | `cancelled`
- Stages / approximate progress: queued 0 → text_extraction 20 → classification 40 → structured_extraction 60 → line_items 80 → completed 100
- Local execution via FastAPI `BackgroundTasks` (replaceable later). Set `DOCUMENT_PROCESSING_SYNC=true` to run inline (used by tests).
- At most one active (`queued`/`running`) job per document; completed/failed jobs remain for history
- Retry creates a new job linked by `parent_job_id` (failed jobs only; no automatic retry loops)
- Cancel is cooperative: queued jobs cancel immediately; running jobs set `cancel_requested` and stop between stages (not a hard thread kill)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/{document_id}/process
curl http://127.0.0.1:8000/api/v1/processing-jobs/{job_id}
curl http://127.0.0.1:8000/api/v1/documents/{document_id}/processing-jobs
curl -X POST http://127.0.0.1:8000/api/v1/processing-jobs/{job_id}/retry
curl -X POST http://127.0.0.1:8000/api/v1/processing-jobs/{job_id}/cancel
```

**Limitation:** This is not distributed queue infrastructure (no Redis/Celery). A future worker process can replace `DocumentProcessingRunner` / `execute_processing_job` without rewriting OCR/classification/extraction.

### Authentication & RBAC (Step 21)

Local JWT authentication (HS256) with roles:

- `viewer` — read documents, validations, reviews, RAG/SQL/investigation
- `operator` — viewer + upload/process/extract/index, validations, relationships, duplicate checks, anomaly scoring, workflow trigger
- `reviewer` — viewer + review actions, duplicate confirm/dismiss, validations
- `admin` — all permissions including user management and model training

```bash
# Set bootstrap password once, then start the API (creates admin only if users table is empty)
# AUTH_BOOTSTRAP_ADMIN_PASSWORD=... in backend/.env

curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"...\"}"

curl http://127.0.0.1:8000/api/v1/auth/me \
  -H "Authorization: Bearer <access_token>"
```

Health (`GET /api/v1/health`) remains public. All other business APIs require a Bearer token.

**Security limitations (foundation only):** no refresh-token rotation, no HttpOnly cookies/CSRF, no rate limiting, no multi-tenant document ownership yet. Frontend role hiding is not a substitute for backend authorization.

### Batch & email attachment ingestion (Step 22)

Provider-independent intake foundation for batch uploads and future email connectors. Actual Gmail / Outlook / IMAP / SES / SendGrid integration is intentionally **not** implemented yet.

Source types:

- `manual_upload` — reserved for the existing single-document upload path identity
- `batch_upload` — multi-file `POST /api/v1/ingestion/batch`
- `email_attachment` — normalized payloads via `POST /api/v1/ingestion/email-attachments`

Configuration:

- `INGESTION_MAX_BATCH_FILES` (default `20`) — reject entire batches larger than this limit
- Per-file size/type limits still use existing document validation (`MAX_UPLOAD_SIZE_MB`, allowed extensions)

Email duplicate protection (separate from Step 15 content duplicates):

- Deterministic `source_identity` = `provider:message_id:filename`
- Resubmitting the same attachment returns the existing document/ingestion as `skipped` / `already_ingested`

Accepted files reuse Step 20 processing jobs (`DocumentProcessingOrchestrator` → `document_processing_jobs`). No second processing pipeline.

Future adapters (IMAP, Gmail API, Microsoft Graph) should implement `EmailAttachmentProvider` and feed `NormalizedEmailAttachment` into `DocumentIngestionService` without changing the ingestion pipeline.

```bash
# Batch (multipart field name: files)
curl -X POST http://127.0.0.1:8000/api/v1/ingestion/batch \
  -H "Authorization: Bearer <token>" \
  -F "files=@a.pdf" -F "files=@b.pdf"

# Mock email attachment (base64 content; no credentials)
curl -X POST http://127.0.0.1:8000/api/v1/ingestion/email-attachments \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d "{\"provider\":\"mock\",\"message_id\":\"mock-message-001\",\"sender\":\"vendor@example.test\",\"subject\":\"Invoice INV-2001\",\"filename\":\"invoice_2001.pdf\",\"content_base64\":\"...\"}"

curl "http://127.0.0.1:8000/api/v1/ingestion?source_type=batch_upload" \
  -H "Authorization: Bearer <token>"
```

RBAC: batch and email ingestion require `documents:write` (operator+). Listing/detail require `documents:read` (authenticated roles with document read).

### Controlled agentic automation (Step 23)

Deterministic, provider-independent agent orchestration over an **explicit read-only tool registry**. Existing RAG, SQL, Investigation, Validation, Anomaly, Review, Duplicate, Workflow, and Document APIs remain independently usable.

- Planner: pattern-based (no LLM required). Unknown intents return `status=unsupported` without guessing tools.
- Execution: bounded by `AGENT_MAX_STEPS` (default 8, hard max 10).
- Tools wrap existing services (no HTTP self-calls, no arbitrary Python/SQL/shell, no approve/reject/delete/email/payment tools).
- Permissions: every tool has a required Step 21 permission; the `/agent/ask` endpoint requires `agent:use` (granted to all authenticated roles).
- Evidence and step metadata are returned; secrets/tokens/passwords are never stored in agent context or audit details.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/agent/ask \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"Why is invoice INV-1827 in review?\",\"max_steps\":8}"

curl "http://127.0.0.1:8000/api/v1/agent/runs" \
  -H "Authorization: Bearer <token>"
```

Configuration:

- `AGENT_MAX_STEPS=8`
- `AGENT_HARD_MAX_STEPS=10`
- `AGENT_MAX_QUESTION_LENGTH=1000`

**Limitation:** This is controlled tool orchestration, not autonomous business action. Future LLM planners can replace the deterministic planner behind the same registry/policy interfaces without rewriting tools.

### Analytics & management reporting (Step 24)

Read-only operational/management analytics over existing data. Analytics do **not** automatically make financial, fraud, or payment decisions.

Endpoints (all require `analytics:read`):

- `GET /api/v1/analytics/summary` — KPI rollup
- `GET /api/v1/analytics/documents` — type/status/processing aggregation
- `GET /api/v1/analytics/invoices` — counts and currency-separated totals
- `GET /api/v1/analytics/vendors` — paginated vendor × currency metrics
- `GET /api/v1/analytics/reviews` — review status/reason/age
- `GET /api/v1/analytics/validations` — invoice↔PO and three-way counts + mismatch dimensions
- `GET /api/v1/analytics/anomalies` — anomaly status counts
- `GET /api/v1/analytics/duplicates` — type/status counts
- `GET /api/v1/analytics/processing` — job status counts + average duration when timestamps exist
- `GET /api/v1/analytics/trends?period=7d|30d|90d|12m` — UTC time-series

Currency handling: invoice totals are always grouped by currency; different currencies are never summed into one financial total.

Filters (where applicable): `date_from`, `date_to`, `document_type`, `status`, `currency`.

## Document Review Queue

Documents that need human verification are automatically placed in a review queue using deterministic rules (not AI/ML), including:

- failed processing
- uncertain / `other` classification
- low classification or extraction confidence
- missing important invoice/PO fields
- invoice vs purchase order validation mismatches
- rule-based vs ML classification disagreement

Review items can be started, approved, or rejected from the Review Queue page.

## RAG Knowledge Assistant

Processed document text is split into overlapping chunks, embedded with a local sentence-transformers model, and stored in PostgreSQL using pgvector.

User questions run semantic retrieval over those chunks. Retrieved context is passed to a configured LLM provider (default: local extractive grounded answerer). Answers include source document citations. If no sufficiently relevant chunks are found, the assistant does not guess.

Local setup notes:

1. PostgreSQL is required. If the host has pgvector installed, the migration enables it and upgrades the embedding column automatically; otherwise embeddings are stored as JSON text and similarity search runs in Python.
2. Install Python deps with `pip install -r requirements.txt`. **`sentence-transformers` is required** for real indexing (it pulls in `torch`). Without it, indexing fails with a clear error and the document stays `processed`.
3. First real embedding run may download `all-MiniLM-L6-v2`.
4. Optional external LLM: set `LLM_PROVIDER=openai`, `LLM_API_KEY=...`, and `LLM_MODEL=...` in `.env` (never commit secrets).
5. Default `LLM_PROVIDER=extractive` answers only from retrieved context without an external API.

This assistant is retrieval-grounded Q&A only. It is not an autonomous agent and cannot take system actions.

## Read-Only SQL Business Data Assistant

Users can ask natural-language questions about structured business data (invoices, purchase orders, vendors, validations, reviews, documents, and indexed chunk metadata).

The system:

1. maps the question to a read-only `SELECT` (deterministic generator by default; optional LLM generator via `SQL_GENERATOR_PROVIDER`)
2. validates the SQL with a hard guard before execution
3. runs the query in a read-only transaction path with row limits
4. returns a concise answer plus structured rows and the generated SQL

Unsafe operations (`INSERT`, `UPDATE`, `DELETE`, `DROP`, etc.) are rejected. This is a controlled read-only SQL capability, not an autonomous database agent and not a write tool.

## Investigation Agent (Step 12)

The Investigation mode runs a **read-only multi-step investigation** over business data.

Supported investigation types (deterministic planner):

- why invoices/documents are sent to review
- validation mismatch patterns and flag breakdowns
- vendor mismatch / repeated vendor issue counts
- documents requiring attention (review queue, failed docs, mismatches)
- missing invoice/PO fields
- low classification or extraction confidence
- invoice totals by vendor
- possible duplicate invoice numbers

Behavior:

1. Maps the question to a controlled investigation plan
2. Executes only pre-approved `SELECT` statements through the Step 11 SQL guard + read-only execution layer
3. Analyzes returned rows into facts / observations / inferences
4. Returns evidence, suggested next review steps (non-executing), and optional technical SQL details

API:

- `POST /api/v1/investigations/ask`

No paid API is required. Deterministic/local mode is the default. The agent does not write data, send notifications, or take autonomous actions.

## Workflow Engine (Step 13)

Controlled, allowlisted internal workflows:

- **Invoice Validation Workflow** (`invoice_extracted`) — validate invoice vs related PO; create/reuse review on mismatch
- **Low Confidence Review Workflow** (`document_processed`) — create review when classification/extraction confidence is below threshold
- **Document Review Workflow** (`review_completed`) — record completion audit metadata

Allowed triggers:

- `document_processed`
- `invoice_extracted`
- `purchase_order_extracted`
- `validation_completed`
- `review_completed`

Allowed actions only:

- `run_validation`
- `create_review`
- `record_result`
- `mark_workflow_completed`

Security restrictions: no shell commands, emails, arbitrary SQL/Python, HTTP calls, or filesystem deletes. Actions call existing application services only.

Executions and step results are stored for audit. Duplicate entity executions and recursive/depth-limited runs are blocked.

API:

- `GET /api/v1/workflows`
- `GET /api/v1/workflows/{workflow_id}`
- `POST /api/v1/workflows/{workflow_id}/trigger`
- `GET /api/v1/workflows/{workflow_id}/executions`
- `GET /api/v1/workflow-executions/{execution_id}`

This is not an autonomous AI workflow builder.

## ML Anomaly Detection (Step 14)

Local statistical anomaly detection for invoices using **scikit-learn IsolationForest**.

Flow:

1. `POST /api/v1/anomalies/train` — train on invoices that have a `total_amount`
2. `POST /api/v1/anomalies/score` — score one or many documents
3. `GET /api/v1/anomalies` — list results with filters/pagination
4. `GET /api/v1/anomalies/{document_id}` — latest result for a document
5. `GET /api/v1/anomaly-model-runs` — training run history

Features (leakage-aware vendor history uses only earlier invoices):

- total / subtotal / tax / tax ratio
- amount vs vendor historical average and median
- vendor historical count and amount deviation
- invoice number presence/digit count
- extraction confidence

Statuses: `normal`, `unusual`, `anomaly`, `requires_review`.

**Important:** anomaly score ≠ fraud. Small datasets are unreliable. Human review is required for important decisions. Training/scoring are explicit operations and are not run automatically during document processing.

## Duplicate Detection (Step 15)

Multi-level duplicate detection for uploaded documents (especially invoices). Findings are **flags for human review only** — the system never auto-deletes, rejects, or modifies documents/invoices/vendors.

### Detection levels

1. **Exact (`exact_duplicate`)** — SHA-256 content hash of the uploaded file bytes (not filename). Hash is computed and stored on upload; matching hashes are flagged when a check runs.
2. **Business (`business_duplicate`)** — invoices with the same normalized vendor name + invoice number. Supporting signals (when present): same currency, same total within tolerance, same invoice date. Missing fields are never invented.
3. **Similar (`similar_duplicate`)** — reuses Step 10 RAG chunk embeddings (averaged cosine similarity) when available; otherwise deterministic Jaccard token similarity on extracted text. Candidate set is filtered by document type / vendor where practical.

### Configuration

| Setting | Default | Meaning |
| --- | --- | --- |
| `DUPLICATE_SIMILARITY_THRESHOLD` | `0.85` | Minimum similarity to flag `similar_duplicate` |
| `DUPLICATE_BUSINESS_AMOUNT_TOLERANCE` | `0.01` | Absolute amount tolerance for “same total” |
| `DUPLICATE_MAX_SIMILARITY_CANDIDATES` | `50` | Cap on similarity comparisons per check |

### Statuses

`pending` → human may set `confirmed` or `dismissed` (or back to `pending`). Similarity is a **signal**, not proof.

### API

- `POST /api/v1/duplicates/check/{document_id}` — run exact/business/similar detection and persist findings
- `GET /api/v1/duplicates` — list with `status`, `detection_type`, pagination, sorting
- `GET /api/v1/duplicates/{document_id}` — candidates for one document
- `PATCH /api/v1/duplicates/{duplicate_id}` — set status (`pending` \| `confirmed` \| `dismissed` only)
- `GET /api/v1/duplicates/summary` — counts by type and status

Upload stores `content_hash` only; expensive similarity checks are **not** run automatically on upload. Use **Check Duplicates** on the Documents page.

### Limitations

- Similarity does not prove duplication.
- Missing invoice fields reduce business matching accuracy.
- OCR errors can affect text/embedding similarity.
- Different legitimate invoices can look similar.
- Human confirmation is required before treating a match as a real duplicate.

## Field Intelligence (Step 16)

Read-only checks on stored invoice and purchase order fields. No second extraction pass and no new tables.

`GET /api/v1/documents/{document_id}/field-intelligence`

Checks invoice number/date, PO number/date, vendor, currency (PKR, USD, EUR, GBP), and amounts. When subtotal, tax, and total are all present, subtotal + tax must match total within `VALIDATION_AMOUNT_TOLERANCE`. Low extraction confidence lowers field confidence and does not fill in missing values.

Actionable results can open one active review with reason `field_missing`, `field_invalid`, `field_suspicious`, or `financial_consistency_mismatch`. Existing review reasons and deduplication stay in place. The endpoint does not approve, reject, delete, or change stored amounts.

The Review Queue details view loads this same endpoint and shows the field evidence plus a plain-language explanation of the review reason. Start, approve, and reject stay manual.

## Tests

```bash
pytest
```

OCR-dependent paths are mocked in automated tests so Tesseract does not need to be installed in CI.

## Docker (Step 25)

Production-oriented image: `backend/Dockerfile` (non-root `appuser`, Tesseract, single uvicorn worker).

Entrypoint runs migrations then starts the API:

```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Use the root `docker-compose.yml` for the full stack. Inside Compose, set:

```env
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@postgres:5432/DATABASE
APP_ENV=production
```

Local non-Docker development continues to use `@localhost` in `DATABASE_URL`.

### Health

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/health` | Liveness (process up) |
| `GET /api/v1/health/ready` | Readiness (PostgreSQL + upload storage); HTTP 503 if not ready |

### Production configuration

When `APP_ENV=production`:

- `DEBUG` is forced off
- OpenAPI docs disabled unless `ENABLE_DOCS=true`
- `AUTH_JWT_SECRET` must be a unique secret ≥ 32 characters (insecure defaults rejected)
- `CORS_ORIGINS` must be an explicit allow-list (no `*`)

Logging format: timestamp, level, logger name, message. Passwords/tokens are redacted from log lines when possible. Audit events remain in `AuditService`.

### Security hardening (Step 26)

| Area | Behavior |
| --- | --- |
| Headers | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`; optional HSTS via `ENABLE_HSTS` (production + HTTPS only) |
| Rate limits | In-process limits for login / upload / AI (`RATE_LIMIT_*_PER_MINUTE`); HTTP 429 — single-instance only |
| Auth | Password strength for new users; login failure cooldown; generic auth error messages |
| Uploads | Sanitized filenames, magic-byte checks, empty/oversized (413) / unsupported rejection |
| Request ID | `X-Request-ID` on responses; included in access logs |
| Indexes | Migration `20260324_0022` for common filter columns |

SQL Agent and Controlled Agent remain allowlisted / read-only with additional regression tests.

### Background workers & email (Step 27)

| Mode | Behavior |
| --- | --- |
| `PROCESSING_WORKER_MODE=local` | FastAPI `BackgroundTasks` (default local) |
| `PROCESSING_WORKER_MODE=celery` | Enqueue `process_document_job` to Redis/Celery |

```bash
celery -A app.workers.celery_app.celery_app worker --loglevel=info
celery -A app.workers.celery_app.celery_app beat --loglevel=info
```

Email: `EMAIL_PROVIDER=none|mock|imap`. IMAP uses stdlib `imaplib` (no OAuth). Poll via Celery Beat or `POST /api/v1/ingestion/email/poll`.

## Project Layout

```
app/
├── api/          # Route handlers
├── core/         # Config, database, logging, exceptions
├── models/       # SQLAlchemy models
├── schemas/      # Pydantic schemas
├── services/     # Business logic / extraction
└── main.py       # Application entrypoint
alembic/          # Database migrations (do not rewrite; latest 20260324_0021)
storage/uploads/  # Local uploaded files (Docker volume in Compose)
tests/            # Test suite
Dockerfile
docker-entrypoint.sh
```
