# SourceHive Frontend (Vite + React)

HR-facing UI + candidate-only AI interview portal.

## Requirements

- Node.js 18+
- Backend running on `http://localhost:8000`

## Setup

From repo root:

```bash
cd frontend
npm install
npm run dev
```

Vite will print the local URL (usually `http://localhost:5173`).

## API Base URL

The API URL is currently defined in `src/api/client.js` as:

```js
const API_BASE = 'http://localhost:8000/api'
```

If you run the backend on a different host/port, update that constant.

## Routes (high level)

- HR app: `/` (dashboard), plus HR pages (roles, analytics, candidates)
- Candidate interview portal (no HR sidebar): `/interview?token=...`
