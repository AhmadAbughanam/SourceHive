# SourceHive Frontend - React

This folder will contain the React frontend for SourceHive.

## Setup

```bash
npm create vite@latest . -- --template react
npm install
npm run dev
```

## Structure

- `/src/components` - React components
- `/src/pages` - Page components
- `/src/api` - API client functions

## Environment

Create a `.env` file:

```
VITE_API_URL=http://localhost:8000/api
```

## API Integration

The frontend connects to the backend at `http://localhost:8000`

Endpoints:

- `GET /api/health` - Health check
- `POST /api/resume/upload` - Upload and process resume
