# DocFlow: AI Document & Workflow Automation

**An AI-assisted platform for accounts-payable documents: upload invoices, purchase orders and goods receipts, read them with OCR, classify and extract their fields, run invoice ↔ PO ↔ GRN 3-way matching, route problems to human review, and ask questions with local AI assistants.**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-20232A?logo=react&logoColor=61DAFB)
![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![scikit-learn](https://img.shields.io/badge/ML-scikit--learn-F7931E?logo=scikitlearn&logoColor=white)
![Tesseract](https://img.shields.io/badge/OCR-Tesseract-5A5A5A)
![JWT](https://img.shields.io/badge/Auth-JWT_+_RBAC-000000?logo=jsonwebtokens&logoColor=white)
![Tests](https://img.shields.io/badge/tests-351_passing-2EA44F)

![Dashboard with document, invoice, review-queue, validation, anomaly, duplicate and processing-job counters](docs/screenshots/dashboard.webp)

## Overview

Finance teams receive invoices, purchase orders (POs) and goods receipt notes (GRNs) as PDFs and scans. Someone has to type the numbers in, check that the invoice matches what was ordered and what was received, chase mismatches, and spot duplicates before anything is paid.

**DocFlow** automates the reading and checking, and keeps people in charge of the decisions:

**Upload → OCR / text extraction → classify → extract fields and line items → validate / 3-way match → human review → analytics and AI assistants**

It is a React single-page app talking to a FastAPI REST API, with data in PostgreSQL. All AI runs **locally**: OCR with Tesseract, classification with scikit-learn, semantic search with sentence-transformers. No document leaves your machine and no paid API key is needed.

## Screenshots

| Documents | Validation and 3-way matching |
|---|---|
| ![Documents library with upload, filters, type, vendor, status badges and per-document actions](docs/screenshots/documents.webp) | ![Invoice to PO validation results: one matched, one mismatch with subtotal, tax and total differences](docs/screenshots/validation.webp) |

| Review queue | Analytics |
|---|---|
| ![Review queue listing documents with reason, priority, status and View / Start Review / Approve / Reject actions](docs/screenshots/review-queue.webp) | ![Operations and management reporting with KPI cards, management report and breakdown charts](docs/screenshots/analytics.webp) |

| AI assistant: business data (SQL) | AI assistant: document knowledge (RAG) |
|---|---|
| ![Business Data tab answering "Show invoice totals by vendor" with a results table](docs/screenshots/ai-assistant-sql.webp) | ![Document Knowledge tab answering a question about invoice INV-1827 with source citations](docs/screenshots/ai-assistant-rag.webp) |

| Invoices | Workflows |
|---|---|
| ![Invoice intake list with extraction status, vendor and review flags](docs/screenshots/invoices.webp) | ![Predefined allowlisted workflows with triggers and allowed actions](docs/screenshots/workflows.webp) |

<details>
<summary><b>Vendors and login pages</b></summary>

![Vendor directory](docs/screenshots/vendors.webp)

![Sign-in page](docs/screenshots/login.webp)

</details>

> Screenshots show the app running locally with fictional sample data (ABC Pvt Ltd, Nova Traders, Zen Office Supplies).

## Problem and solution

| Problem | How DocFlow solves it |
|---|---|
| Invoice data is typed in by hand from PDFs and scans | Text extraction from PDFs, Tesseract OCR (with image pre-processing) for scans and photos |
| Every document has to be sorted by type | Hybrid classifier: rules + a local TF-IDF / Logistic Regression model, with confidence scores |
| Invoices are paid without checking the PO and the delivery | Invoice ↔ PO validation and **3-way matching** (vendor, PO/GRN references, line-item quantities, amounts, document links) |
| The same invoice is submitted twice | Exact (SHA-256), business (vendor + invoice number) and content-similarity duplicate detection, run automatically |
| Problems are found too late, or not at all | A review queue with reasons and priorities; a person approves or rejects |
| Managers can't see what is happening | Dashboard and analytics: volumes, invoice value per currency, mismatches, review workload, trends |
| Answers are buried in documents and tables | AI assistants: document Q&A with citations, read-only business-data questions, investigations |

## Features

| Module | What it does |
|---|---|
| **Documents** | Upload single files or batches (PDF, PNG, JPG; DOCX/XLSX/CSV stored); background processing jobs with progress, retry and cancel |
| **OCR and extraction** | Selectable PDF text, OCR fallback for scans; invoice, PO and GRN header fields; line items from tables and `Label: value` layouts |
| **Classification** | Rule-based + ML hybrid (invoice, purchase order, goods receipt, contract, receipt, bank statement, other); model retrains automatically when outdated |
| **Validation** | Invoice ↔ PO comparison of vendor, currency, subtotal, tax and total, with a mismatch summary |
| **3-way matching** | Invoice ↔ PO ↔ GRN with an explainable result per check: matched / mismatch / needs review |
| **Document relationships** | Suggested links by PO and GRN numbers; a person confirms them |
| **Duplicates** | Exact, business and similarity duplicates, flagged on the document; confirm or dismiss |
| **Review queue** | Reviews created for failed processing, low confidence, missing fields and mismatches; start / approve / reject |
| **Vendors** | Vendor directory linked automatically from extracted documents |
| **Anomalies** | Local IsolationForest model scores unusual invoices (statistical, not a fraud verdict) |
| **Workflows** | Predefined, allowlisted workflows triggered by events (document processed, invoice extracted, review completed) |
| **AI assistant** | Document Knowledge (RAG with citations), Business Data (natural language → validated read-only SQL), Investigation, Controlled Agent |
| **Analytics** | KPIs, management report, document types and status, invoice value per currency, trends |
| **Security** | JWT login, roles (admin, reviewer, operator, viewer), audit logs, rate limits, login lockout, password rules, upload content checks |

## Architecture

```mermaid
flowchart LR
    U[User] --> FE[React 18 + Vite SPA<br/>React Router]
    FE -- "fetch + JWT<br/>/api/v1/*" --> API[FastAPI<br/>REST API]
    API --> AUTH[JWT auth + RBAC<br/>rate limits, audit log]
    AUTH --> SVC[Services<br/>documents, extraction, validation,<br/>3-way match, reviews, workflows]
    SVC --> JOBS[Processing jobs<br/>BackgroundTasks or Celery + Redis]
    JOBS --> OCR[Text extraction<br/>pypdf, Tesseract OCR]
    JOBS --> ML[Local ML<br/>TF-IDF classifier, IsolationForest,<br/>sentence-transformers]
    SVC --> DB[(PostgreSQL<br/>SQLAlchemy + Alembic)]
    JOBS --> DB
    SVC --> FS[(Local file storage<br/>storage/uploads)]
```

**Document lifecycle**

```mermaid
flowchart LR
    A[Upload] --> B[Extract text / OCR]
    B --> C[Classify]
    C --> D[Extract fields + line items]
    D --> E[Index for search + duplicate check]
    E --> F{Validation / 3-way match}
    F -- matched --> G[Done]
    F -- mismatch or low confidence --> H[Review queue]
    H -- approve / reject --> G
```

1. Uploading a file stores it and creates a processing job (run in the background).
2. The job extracts text (OCR for images and scanned PDFs), classifies the document and extracts invoice / PO / GRN fields and line items.
3. The document is indexed for semantic search and checked for duplicates; events trigger allowlisted workflows (for example, invoice validation).
4. Anything uncertain or inconsistent goes to the review queue. The system **never** approves or blocks a payment by itself.

## Tech stack

<img src="https://skillicons.dev/icons?i=python,fastapi,react,vite,js,postgres,redis,docker,sklearn" alt="Python, FastAPI, React, Vite, JavaScript, PostgreSQL, Redis, Docker, scikit-learn">

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite 5, React Router 6, CSS |
| Backend | Python, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, PyJWT, bcrypt |
| Database | PostgreSQL (pgvector optional; works without it) |
| Documents and OCR | pypdf, pypdfium2, Pillow, Tesseract (pytesseract) |
| Machine learning | scikit-learn (TF-IDF + Logistic Regression, IsolationForest), sentence-transformers (all-MiniLM-L6-v2) |
| Workers | FastAPI BackgroundTasks (default) or Celery + Redis |
| Tests and tooling | pytest (351 tests), Docker Compose, nginx |

## Project structure

```text
DocFlow-AI-Document-Automation/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, middleware, router
│   │   ├── api/routes/          # auth, documents, ingestion, validations, reviews, rag, sql, agent, ...
│   │   ├── core/                # config, database, security, permissions, rate limits
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic request / response models
│   │   ├── services/            # OCR, classification, extraction, matching, duplicates, RAG, SQL, agent
│   │   ├── workers/             # Celery app and tasks
│   │   └── data/classification/ # starter training set for the classifier
│   ├── alembic/                 # database migrations
│   ├── tests/                   # pytest suite
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/               # Dashboard, Documents, Invoices, Validation, ReviewQueue, AIAssistant, ...
│   │   ├── components/          # modals, layout, AI and review components
│   │   ├── services/            # API clients
│   │   └── auth/                # auth context, protected routes, permissions
│   └── vite.config.js           # dev server on 5174, proxies /api to the backend
├── samples/                     # sample invoice / PO / GRN files + generator script
├── docs/screenshots/            # README images
└── docker-compose.yml           # optional production-like stack
```

## Getting started

### Prerequisites

- [Python](https://www.python.org/) 3.11 or higher
- [Node.js](https://nodejs.org/) 18 or higher and npm
- [PostgreSQL](https://www.postgresql.org/) 14 or higher
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (for images and scanned PDFs)

### 1. Clone

```bash
git clone https://github.com/Bhavish295/DocFlow-AI-Document-Automation.git
cd DocFlow-AI-Document-Automation
```

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
copy .env.example .env          # Windows  (cp on macOS / Linux)
```

Create an empty database (for example `docflow`) in PostgreSQL, then edit `backend/.env`:

| Variable | Description |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://USER:PASSWORD@localhost:5432/docflow` |
| `AUTH_JWT_SECRET` | Secret used to sign login tokens. Use a long random value |
| `AUTH_BOOTSTRAP_ADMIN_PASSWORD` | Password for the first `admin` user, created when the users table is empty |
| `TESSERACT_CMD` | Full path to `tesseract.exe` on Windows if it is not on PATH |
| `CORS_ORIGINS` | Allowed frontend origins (default includes `http://localhost:5174`) |

Run the migrations and start the API:

```bash
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: **http://localhost:8000/docs**

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5174** and sign in as `admin` with the bootstrap password. New users are created by an admin on the **Users** page (there is no public sign-up; this is an internal business tool).

### 4. Try it with the sample files

Upload `samples/sample_invoice.pdf`, `samples/sample_purchase_order.pdf` and `samples/sample_goods_receipt.pdf`, process them, confirm the suggested relationships, then run a 3-way match on the **Validation** page. All checks should come out **matched**. Run `python samples/generate_samples.py` to regenerate the files.

### Scripts

| Command | Location | Description |
|---|---|---|
| `uvicorn app.main:app --reload` | backend | Start the API |
| `alembic upgrade head` | backend | Apply database migrations |
| `pytest` | backend | Run the test suite (351 tests) |
| `npm run dev` | frontend | Start the Vite dev server |
| `npm run build` | frontend | Production build |
| `docker compose up --build` | root | Optional stack: frontend, backend, postgres, redis, Celery worker and beat |

## API endpoints

All routes except `health` and `auth/login` need an `Authorization: Bearer <token>` header. Permissions depend on the user's role. Full interactive docs are at `/docs`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Health check (`/health/ready` for readiness) |
| `POST` | `/api/v1/auth/login` | Log in and receive a JWT |
| `GET` | `/api/v1/auth/me` | Current user |
| `GET` / `POST` | `/api/v1/documents` | List / upload documents |
| `POST` | `/api/v1/documents/{id}/process` | Queue OCR, classification and extraction |
| `GET` | `/api/v1/documents/{id}/invoice` · `/purchase-order` · `/goods-receipt` · `/line-items` | Extracted data |
| `POST` | `/api/v1/ingestion/batch` | Upload and process many files at once |
| `GET` | `/api/v1/document-relationships/suggestions/{id}` | Suggested invoice / PO / GRN links |
| `POST` | `/api/v1/validations/invoice/{invoice_id}/purchase-order/{po_id}` | Invoice ↔ PO validation |
| `POST` | `/api/v1/validations/three-way` | Invoice ↔ PO ↔ GRN 3-way match |
| `GET` / `PATCH` | `/api/v1/reviews` · `/reviews/{id}` | Review queue; `start`, `approve`, `reject` actions |
| `GET` / `PATCH` | `/api/v1/duplicates` · `/duplicates/{id}` | Duplicate findings; confirm or dismiss |
| `POST` | `/api/v1/rag/ask` | Document question answering with citations |
| `POST` | `/api/v1/sql/ask` | Natural-language business question → validated read-only SQL |
| `POST` | `/api/v1/investigations/ask` · `/agent/ask` | Investigation and controlled agent |
| `GET` | `/api/v1/analytics/summary` | Dashboard KPIs (more under `/analytics/*`) |
| `GET` / `POST` | `/api/v1/vendors` · `/workflows` · `/users` · `/audit-logs` | Vendors, workflows, users (admin), audit trail |

## Troubleshooting

| Issue | Solution |
|---|---|
| Login fails for `admin` | `AUTH_BOOTSTRAP_ADMIN_PASSWORD` only works on an empty users table; if the admin already exists, use its original password |
| Images or scanned PDFs have no text | Install Tesseract and set `TESSERACT_CMD` in `backend/.env` |
| "Indexing failed" on documents | The first run downloads the embedding model; check the internet connection once, then restart the backend |
| `extension "vector" is not available` | Not needed: DocFlow works without pgvector |
| CORS or network errors | Make sure the backend runs on port 8000 and your frontend URL is in `CORS_ORIGINS` |
| Every document is in the review queue | Expected with few documents: classification confidence is below the 0.70 review threshold for short samples |

## Security notes

- Never commit `.env` files. Only `.env.example` templates are in the repository.
- Change `AUTH_JWT_SECRET` before any shared deployment; with `APP_ENV=production` the app refuses weak secrets.
- Passwords are hashed with bcrypt; secrets are scrubbed from audit logs.
- The SQL assistant only runs validated, read-only `SELECT` queries; the agent can only call allowlisted read-only tools.
- Rate limits and login lockout are in-process (single instance). Use a shared store such as Redis for multiple instances.

## Future improvements

These are **not implemented yet**:

- An LLM provider option for free-form questions (the assistants are rule-based and deterministic today)
- Smarter extraction for more invoice layouts and multi-page tables
- Tuning classification confidence so clear documents skip the review queue
- Self-service sign-up with admin approval
- Email reminders for pending reviews
- Cloud deployment (object storage, managed PostgreSQL, HTTPS) and a hosted demo

## License

ISC

## Author

**Bhavish Kumar**: Full Stack Developer · AI Automation Engineer · Backend Developer

[GitHub](https://github.com/Bhavish295) · [LinkedIn](https://www.linkedin.com/in/bhavish-kumar-ab40a9303) · [Portfolio](https://bhavishkumar-portfolio.netlify.app/)
