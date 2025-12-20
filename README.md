# SourceHive

Resume intake + HR dashboard + AI interview portal.

## Architecture

- Backend: FastAPI (`backend/main.py`)
- Frontend: Vite + React (`frontend/`)
- Database: MySQL 8 (schema in `setup.sql`)
- Search: MySQL-backed filtering (prototype)

## Quick start (recommended)

### 1) Start the database (Docker)

From repo root:

```bash
docker compose up -d
```

MySQL is exposed on host port `3308`.

### 2) Run the backend

```bash
cd backend
python -m venv venv
./venv/Scripts/activate   # Windows (PowerShell: .\venv\Scripts\Activate.ps1)
pip install -r ../requirements.txt
python main.py
```

API: `http://localhost:8000`  
Docs: `http://localhost:8000/docs`

### 3) Run the frontend

```bash
cd frontend
npm install
npm run dev
```

UI: usually `http://localhost:5173`

## Key features

- CV upload (PDF/DOCX/images), parsing, and data storage
- HR dashboard with filters + candidate profile view + notes
- Roles management (JD + keywords + visibility)
- Analytics dashboard
- Candidate-only AI interview portal with token links

## Configuration

- Backend environment: `backend/App/.env` (auto-loaded by `backend/main.py`)
- Frontend API base URL: `frontend/src/api/client.js`

## Documentation

- Backend details: `backend/README.md`
- Frontend details: `frontend/README.md`
- Local model card (optional): `backend/model/MODEL_CARD.md`

