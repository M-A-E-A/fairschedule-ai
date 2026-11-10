# FairSchedule AI

FairSchedule AI is a demo multi-tenant university scheduling system built with FastAPI, React, TypeScript, and OR-Tools. The project includes a public landing page, a tenant-aware backend, a dashboard, a simplified scheduler, and a basic AI assistant mode.

## Architecture

- `frontend/`: Vite + React + TypeScript app
- `backend/`: FastAPI API, ORM, scheduler, authentication and seed data
- `docs/`: supplemental product notes
- `docker-compose.yml`: local Postgres and app orchestration

## Features

- Tenant-aware institutions and campuses
- User roles and authorization checks
- Demo seed data for multiple institutions
- Timetable generation using OR-Tools CP-SAT
- Repair proposal generation and audit log
- AI assistant stub that works without external keys
- 3D campus visualization with React Three Fiber
- Public landing page with GSAP scroll animations

## Local setup

```bash
cd backend
python -m venv .venv
. .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
alembic upgrade head           # create the schema (Alembic migrations)
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`DATABASE_URL` defaults to SQLite (`fairschedule.db`) for local runs; set it to a
PostgreSQL URL when using the Compose `db` service. After editing models, create a
migration with `alembic revision --autogenerate -m "describe change"` and re-run
`alembic upgrade head`.

In another terminal:

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

Or with Docker Compose (Postgres + backend + frontend):

```bash
docker compose up --build
```

## Demo credentials

Sign in on the login page with **either** the account username **or** its email
address (toggle the tabs), using these development-only accounts:

- admin (username `admin`) or admin@northbridge.edu / demo-admin
- operator (username `operator`) or operator@northbridge.edu / demo-operator
- faculty (username `faculty`) or faculty@northbridge.edu / demo-faculty
- student (username `student`) or student@northbridge.edu / demo-student

These are development-only accounts.

## Testing

Backend:

```bash
cd backend
python -m pytest -q
python -m ruff check .
```

Frontend:

```bash
cd frontend
npm run lint
npm run test -- --run
npm run build
```

## CI

The repository includes GitHub Actions for backend tests and frontend build checks.
