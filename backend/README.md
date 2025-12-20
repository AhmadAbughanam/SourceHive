# SourceHive Backend (FastAPI)

FastAPI service that powers resume upload/parsing, HR dashboards, and AI interview sessions.

## Requirements

- Python 3.9+
- MySQL 8 (local or Docker)
- For image/scanned CVs: **Tesseract OCR** installed and available on `PATH` (`tesseract --version`)

## Setup (Windows / PowerShell)

From repo root:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r ..\requirements.txt
```

## Database (recommended: Docker)

From repo root:

```powershell
docker compose up -d
```

- MySQL is exposed on host port `3308` (container `3306`)
- Schema is initialized from `setup.sql`

## Configuration (`backend/App/.env`)

`backend/main.py` automatically loads `backend/App/.env`.

Minimum DB settings typically look like:

```env
DB_HOST=127.0.0.1
DB_PORT=3308
DB_USER=cv
DB_PASSWORD=password
DB_NAME=cv
```

Optional interview + email settings:

```env
INTERVIEW_BASE_URL=http://localhost:5173/interview
INTERVIEW_MAX_QUESTIONS=6

SMTP_HOST=smtp.hostinger.com
SMTP_PORT=587
SMTP_USE_TLS=1
SMTP_USER=info@yourdomain.com
SMTP_PASSWORD=your_password
SMTP_FROM=info@yourdomain.com
```

Optional LLM settings (see `model/MODEL_CARD.md`):

```env
LLM_PROVIDER=auto  # auto|ollama|llama_cpp
OLLAMA_URL=http://127.0.0.1:11434/api/chat
OLLAMA_MODEL=qwen2.5:7b-instruct
LOCAL_LLM_PATH=backend/model/Llama-3.2-3B-Instruct-Q4_0.gguf
```

## Run

From `backend/`:

```powershell
.\venv\Scripts\Activate.ps1
python main.py
```

API will be available at:

- `http://localhost:8000/api/health`
- Swagger UI: `http://localhost:8000/docs`

## Key Endpoints (selected)

- `POST /api/resume/upload` (multipart) — upload + parse + store
- `GET /api/hr/applications` — applications list (filters/pagination)
- `GET /api/hr/applications/{id}` — candidate profile (HR view)
- `POST /api/interviews/invite` — create token invite + send email
- `GET /api/interviews/by-token?token=...` — candidate portal session
- `POST /api/interviews/by-token/start?token=...` — start interview
- `POST /api/interviews/by-token/message?token=...` — chat turn

## Troubleshooting

- **MySQL connection errors (`127.0.0.1:3306`)**: your MySQL container is mapped to `3308`; set `DB_PORT=3308` in `backend/App/.env`.
- **OCR dependencies missing**: install Tesseract and confirm `tesseract --version` works in the same terminal where you run the backend.

