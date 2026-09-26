# Document & Workflow Automation — Frontend

React application shell for the DocFlow platform.

## Setup

```bash
cd frontend
npm install
```

Optional: copy `.env.example` to `.env` and set `VITE_API_BASE_URL` only if the API is on a different origin. Leave it empty (default) so the browser uses same-origin `/api` (Vite proxy in development, nginx in Docker).

## Development

```bash
npm run dev
```

Open the URL Vite prints (configured port is often `5174`; Docker maps production UI to host `5173`).

The Vite dev server proxies `/api` requests to `http://127.0.0.1:8000`.

## Build

```bash
npm run build
npm run preview
```

## Docker / production static hosting

`frontend/Dockerfile` is a multi-stage build:

1. `npm ci` + `npm run build`
2. nginx serves `dist/` with SPA `try_files` fallback
3. nginx proxies `/api/` to the Compose service `backend:8000`

Do not run the Vite dev server in production containers.

## Structure

```
src/
├── components/layout/   # App shell, sidebar, header
├── config.js            # VITE_API_BASE_URL helpers
├── data/                # Navigation configuration
├── pages/               # Route-level views
├── services/            # API clients
└── styles/              # Global design tokens and base styles
```
