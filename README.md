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
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

## Demo credentials

- admin@northbridge.edu / demo-admin
- operator@northbridge.edu / demo-operator
- faculty@northbridge.edu / demo-faculty
- student@northbridge.edu / demo-student

These are development-only accounts.

## Testing

```bash
cd backend
pytest -q
cd ../frontend
npm run test -- --run
npm run build
```

## CI

The repository includes GitHub Actions for backend tests and frontend build checks.
