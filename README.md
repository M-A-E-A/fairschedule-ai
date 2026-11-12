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
- Timetable publish workflow: named, versioned snapshots of the institution's
  timetable with an added/removed/moved diff against the live draft
- CSV import for institution data (rooms, courses, lecturers, student groups)
  with all-or-nothing, per-row validation errors
- Repair proposal generation and audit log
- AI assistant stub that works without external keys
- 3D campus visualization with React Three Fiber: buildings colored by live
  occupancy for a chosen day/time window, click a building for its day schedule
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

`DATABASE_URL` defaults to SQLite (`sqlite:///./demo.db`) for local runs; set it to a
PostgreSQL URL when using the Compose `db` service (use the
`postgresql+psycopg://…` scheme — psycopg 3 is the installed driver). After editing
models, create a
migration with `alembic revision --autogenerate -m "describe change"` and re-run
`alembic upgrade head`.

`SOLVER_TIME_LIMIT_SECONDS` (default `10`) caps the wall-clock time of the CP-SAT
solve behind `POST /schedules/generate`, so a large institution cannot hang the
request and pin a worker. When the solver cannot finish inside the budget, the
response reports status `UNKNOWN` (never a partial result presented as a full
schedule: the deterministic fallback assignment — which honours every hard
constraint — is served with `solution_source: "greedy_fallback"`), and the
`metrics` block exposes `solver_status` and `time_to_generate_ms`. A request may
override the default once with `time_limit_seconds` in the JSON body.

In another terminal:

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

Or with Docker Compose (Postgres + backend + production-built frontend served by
nginx on http://localhost:5173):

```bash
docker compose up --build
```

The frontend image is a multi-stage build (`npm run build`, then nginx serving
the static bundle with SPA fallback routing); the backend runs against the
Compose Postgres service. The backend generates an ephemeral JWT secret per
process (`APP_ENV=development`), so no secret is committed for the stack.

## CSV import (institution data)

`POST /institutions/{id}/import/{dataset}` accepts a UTF-8 CSV file
(multipart field `file`) for one of `rooms`, `courses`, `lecturers`, or
`student-groups` and applies it **all-or-nothing**: every row is validated
first, so a single bad row imports nothing. A rejected file returns `400`
listing *every* failing row with its row number as it appears in the file
(header = row 1) and the reason.

| dataset         | required columns          | optional columns               |
|-----------------|---------------------------|--------------------------------|
| `rooms`         | `campus_id,name,capacity` | `room_type,equipment`          |
| `courses`       | `code,name`               | `required_room_type`           |
| `lecturers`     | `name,email`              | —                              |
| `student-groups`| `name,size`               | —                              |

Requires an administrator or campus-operator bearer token, and rows are only
ever written into the caller's own institution — another tenant's institution
id is refused with `403`, and a campus id outside the tenant is a per-row
error. Parsing uses the Python standard library `csv` module; no extra
dependencies. Every successful import records a `csv_import` audit event.

```bash
# rooms.csv: campus_id,name,capacity,room_type,equipment
curl -X POST http://localhost:8000/institutions/1/import/rooms \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@rooms.csv"
```

## Demo credentials

Sign in on the login page with **either** the account username **or** its email
address (toggle the tabs), using these development-only accounts:

- admin (username `admin`) or admin@northbridge.edu / demo-admin
- operator (username `operator`) or operator@northbridge.edu / demo-operator
- faculty (username `faculty`) or faculty@northbridge.edu / demo-faculty
- student (username `student`) or student@northbridge.edu / demo-student

A second seeded tenant demonstrates the multi-tenant isolation:

- harbor-admin (username `harbor-admin`) or admin@harbor.edu / demo-admin-harbor
  — administrator of **Harbor College**, a separate institution whose rooms,
  courses, and timetable are invisible to the Northbridge accounts above.

These are development-only accounts.

## Testing

Backend:

```bash
cd backend
python -m pytest -q
python -m ruff check .
```

The suite pins itself to a throwaway SQLite database unless `DATABASE_URL` is set
in the environment — with it set (for example to a `postgresql+psycopg://…` URL)
the same suite runs against that database, applying `alembic upgrade head` first.
That is exactly what the CI "Backend (PostgreSQL 16)" job does.

Frontend:

```bash
cd frontend
npm run lint
npm run test -- --run
npm run build
```

## CI

The repository includes GitHub Actions for backend tests and frontend build checks.
