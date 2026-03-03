# AI Library Management System

Production-style library management system with secure authentication and AI-assisted retrieval.

## Features

- Book management CRUD (create, read, update, delete) with role-based permissions
- Check-out / check-in workflow with loan tracking
- Search by title, author, and status
- Auth0 SSO with role-based access (`admin`, `librarian`, `member`)
- AI semantic chat search (RAG) over catalog data
- Prompt-injection guardrails and fallback behavior when AI is unavailable

## Tech Stack

- Backend (Python): FastAPI, SQLAlchemy, Alembic, PostgreSQL/SQLite, Pytest
- Frontend (TypeScript): React, Vite, TanStack Query
- Auth: Auth0 JWT validation + RBAC claims
- AI: OpenAI (embeddings + generation) for conversational catalog Q&A

## Project Structure

- `backend/`: FastAPI API, models, migrations, tests
- `frontend/`: React web app

## Prerequisites

- Python 3.11+
- Node.js 18+
- npm 9+

## Environment Variables

Copy examples first:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

### Backend (`backend/.env`)

```env
DATABASE_URL=sqlite:///./library.db
APP_ENV=development
AUTH0_DOMAIN=
AUTH0_AUDIENCE=
AUTH_DISABLE_JWT_VERIFICATION=true
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
AI_RAG_TOP_K=5
AI_CHAT_MEMORY_TURNS=8
AI_CHAT_SESSION_TTL_MINUTES=180
FRONTEND_ORIGIN=http://localhost:5173
```

### Frontend (`frontend/.env`)

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_AUTH0_ENABLED=false
VITE_AUTH0_DOMAIN=
VITE_AUTH0_CLIENT_ID=
VITE_AUTH0_AUDIENCE=
```

## Run Locally

### 1) Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

### 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

### Local URLs

- Frontend: `http://localhost:5173`
- Backend API docs: `http://localhost:8000/docs`

## Authentication Modes

### Development Mode (quick local testing)

Set in backend env:

```env
AUTH_DISABLE_JWT_VERIFICATION=true
```

Use bearer tokens in format:

- `admin:admin@example.com`
- `librarian:lib@example.com`
- `member:user@example.com`

Example:

```bash
curl -H "Authorization: Bearer admin:admin@example.com" http://localhost:8000/api/books
```

### SSO Mode (Auth0)

Set in backend env:

```env
AUTH_DISABLE_JWT_VERIFICATION=false
AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_AUDIENCE=https://your-api-audience
```

Set in frontend env:

```env
VITE_AUTH0_ENABLED=true
VITE_AUTH0_DOMAIN=your-tenant.us.auth0.com
VITE_AUTH0_CLIENT_ID=your_spa_client_id
VITE_AUTH0_AUDIENCE=https://your-api-audience
```

Auth0 must include role claims in access tokens under:

- `https://library-ai.example.com/roles`

## Tests

### Backend

```bash
cd backend
pytest -q
```

### Frontend

```bash
cd frontend
npx vitest run
npm run build
```

## AI Evaluation Suite

Run deterministic evaluation:

```bash
cd backend
python scripts/eval_chat_suite.py --strict
```

Run with live OpenAI calls:

```bash
cd backend
python scripts/eval_chat_suite.py --live-openai --top-k 5
```

## Deployment

- Backend: Render
- Frontend: Vercel
- Database: Neon PostgreSQL

Live URLs:

- Frontend: `<your-vercel-url>`
- Backend: `<your-render-url>`

## Notes

- Do not commit secrets (`.env`, API keys, passwords).
- Use separate role accounts for role-based testing in production SSO mode.
