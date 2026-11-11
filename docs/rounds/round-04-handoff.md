# Round 4 handoff — scope extension S-01..S-13

STATUS: IN PROGRESS

This file is a living document: it is updated and committed alongside every scope
milestone, so a successor session can resume from the commits plus this file.
The mandate is [`docs/rounds/round-04-scope.md`](round-04-scope.md) (items S-01
through S-13, tier order). Round-3 state: `R-001`–`R-015` all resolved and
verified; none may be reintroduced.

## Progress tracker

| Item | Title | Status | Commit |
|------|-------|--------|--------|
| S-01 | Solver time limit | done | `3f48122` |
| S-02 | Rate-limiter persistence | done | `bdc36c4` |
| S-03 | PostgreSQL exercised in CI | done | `dc14dd8` |
| S-04 | Docker build + container smoke test in CI | done | `8cf3370` |
| S-05 | 3D campus ↔ schedule integration | done | (this commit) |
| S-06 | Timetable publish workflow | pending | — |
| S-07 | CSV import | pending | — |
| S-08 | ICS calendar export | pending | — |
| S-09 | Audit timeline UI | pending | — |
| S-10 | Solver metrics dashboard | pending | — |
| S-11 | Route-level code splitting | pending | — |
| S-12 | Playwright E2E smoke tests | pending | — |
| S-13 | Coverage and mypy gates | pending | — |

## Environment facts (unchanged from rounds 1–3)

Docker, Redis, and a local PostgreSQL server are **not installed** on the
development machine. The S-03 (PostgreSQL) and S-04 (Docker) jobs are CI-only by
design per the scope doc's exemption; they will be reported here as CI runs,
never as local runs. Everything else runs both locally and in CI.

## Milestone log

(Appended after each milestone: items done, raw gate output, commit SHA.)

### S-01 — solver time limit (commit: this milestone's)

The CP-SAT wall-clock budget was made env-configurable and the honest-status
contract pinned down by tests:

- `Settings.solver_time_limit_seconds` (default `10.0`, `gt=0`), documented in
  `.env.example` and the README (`SOLVER_TIME_LIMIT_SECONDS`).
- `ScheduleGenerateRequest.time_limit_seconds` is now an optional per-request
  override; when omitted, `POST /schedules/generate` resolves the budget from
  `get_settings().solver_time_limit_seconds`.
- The engine already enforced `solver.parameters.max_time_in_seconds` and
  reported the solver status verbatim (including `UNKNOWN`); on timeout it
  serves the deterministic greedy fallback — a *complete* conflict-free
  schedule, never a partial result presented as full — with
  `solution_source: "greedy_fallback"` and the honest `UNKNOWN` status.
  Verified empirically: a 40-session/3-room instance with the default 10 s
  budget takes 11.0 s wall (the budget is genuinely load-bearing); with a
  1e-7 s budget it returns `UNKNOWN` + full fallback in 0.8 s.
- The response already exposes `status`, `metrics.solver_status`, and
  `metrics.time_to_generate_ms` (docs/PROJECT.md evaluation metrics; feeds
  S-10).
- New tests: `backend/tests/test_solver_time_limit.py` — (a) solvable instance
  within the budget, (b) artificially tiny budget → honest `UNKNOWN` + complete
  fallback + zero violations, (c) env-var mapping into `Settings` and the
  configured default reaching the solver through the API, plus the explicit
  per-request override still winning. The instance-patch pattern matches the
  existing `tests/test_sso.py` fixture style (no `cache_clear`, which would
  fork the cached Settings instance some modules hold directly — that exact
  interaction was found and avoided while writing the tests).

Raw local gate output (backend):

```
$ python -m ruff check .
All checks passed!

$ python -m pytest -q
121 passed, 1 warning in 27.12s
```

(115 tests before this round + 6 new S-01 tests; the 1 warning is the known
anyio `BlockingPortal` DeprecationWarning from starlette's TestClient, present
since round 1.)

### S-02 — rate-limiter persistence (commit: this milestone's)

The in-memory `defaultdict` failure store was replaced by the `loginattempt`
database table, so every worker/replica of a deployment counts the same
sliding window and a fresh process inherits previously recorded failures:

- New SQLModel table `LoginAttempt` (`client_ip`, `identifier`, wall-clock
  `failed_at`, composite index on the key, index on `failed_at`) in
  `app/models/tenant.py`, created by Alembic migration `a1c4e7f9d2b3`
  (chained after `72bbb9943009`); `alembic/env.py` imports the model so
  future autogeneration sees it.
- `LoginRateLimiter` methods now take the request's `Session`; every operation
  commits its own transaction — a failed login raises `HTTPException` *after*
  recording the failure, and an uncommitted row would be rolled back when the
  request session closes. Wall-clock UTC timestamps (naive, so they
  round-trip identically on SQLite and PostgreSQL) replace `time.monotonic()`,
  which resets per process and would break exactly the property the
  persistent store exists for.
- Sliding-window semantics, key shape `(client IP, attempted identifier)`,
  unknown/known-account equivalence, and the R-014 dummy-hash timing
  equalization are unchanged; `app/api/auth.py` only passes its existing
  session into the limiter calls.
- Expired attempts are pruned globally on every operation
  (`failed_at <= now - window`), so the table cannot grow unboundedly.
- `tests/conftest.py` applies `alembic upgrade head` once at import (the
  lifespan re-applies it as a no-op) so the throttle table exists even for
  tests that never boot the app, and the `_fresh_login_throttle` autouse
  fixture now clears the table through a real session. It also now respects
  an explicit `DATABASE_URL` environment variable instead of forcing SQLite —
  the hook S-03's CI job uses (local SQLite default unchanged).
- New tests: `backend/tests/test_rate_limit_persistence.py` — lockout
  survives a fresh `LoginRateLimiter` instance (directly and end-to-end via
  HTTP with the module's limiter swapped), failures are shared between two
  concurrent instances (two workers), expired attempts are pruned and do not
  count, the window slides to unlock, and success deletes the rows. The
  six R-014 tests in `tests/test_login_throttle.py` pass **unchanged**
  (`git diff` shows no modification to that file).

Raw local gate output (backend):

```
$ python -m ruff check .
All checks passed!

$ python -m pytest -q
127 passed, 1 warning in 35.81s
```

(121 after S-01 + 6 new S-02 tests.)

### S-03 — PostgreSQL exercised in CI (commit: this milestone's)

- New CI job **Backend (PostgreSQL 16)** in `.github/workflows/ci.yml`: a
  `postgres:16` service container with health checks, `pip install` of the
  backend requirements, an explicit `alembic upgrade head` against the
  service, then the full `pytest -q` suite with `DATABASE_URL` pointing at
  it. The existing `backend`/`frontend` jobs are byte-identical to before.
- `tests/conftest.py` (changed under S-02) respects an explicit
  `DATABASE_URL` environment variable; with none set the local default is
  exactly the old throwaway SQLite file.
- Driver finding while wiring this up (the dialect-specific class of issue
  this job exists to catch, found statically before the first run): only
  `psycopg` (v3) is installed — `psycopg2` is not — so SQLAlchemy URLs must
  use the `postgresql+psycopg://` scheme. A bare `postgresql://` URL raises
  `Can't load plugin: sqlalchemy.dialects:postgresql:psycopg2`. Fixed in the
  CI job env, `docker-compose.yml` (whose `DATABASE_URL` could never have
  worked with the installed driver — the stack has never been executed, per
  the R-009/R-015 disclosure), and `.env.example`; README documents the
  scheme. The full migration chain (`72bbb9943009` → `a1c4e7f9d2b3`) now runs
  against a real PostgreSQL server in this job.
- **Not run locally** — no PostgreSQL server on the development machine; this
  job is CI-only by the scope doc's exemption. Local SQLite gates:

```
$ python -m ruff check .
All checks passed!

$ python -m pytest -q
127 passed, 1 warning in 35.81s
```

CI result for the new job on this commit: recorded in the Interim failures /
final sections below once observed.

**S-03 CI result (run `43047958410` on `dc14dd8`, all jobs green):** the
*Backend (PostgreSQL 16)* job passed on the first push — `alembic upgrade head`
applied both revisions to the `postgres:16` service, then the suite reported
`127 passed, 2 warnings in 20.69s` (the second warning is the disclosed
Linux-only passlib `crypt` notice, matching rounds 1–3; local SQLite runs
report 1 warning for the same reason). No dialect-specific failures were
found on the first run: the psycopg URL scheme issue was caught statically
before the push (documented above). Run URL:
https://github.com/M-A-E-A/fairschedule-ai/actions/runs/43047958410

### S-04 — Docker build + container smoke test in CI (commit: this milestone's)

- New CI job **Docker (build + container smoke test)**: `docker build` of both
  images (`./backend`, `./frontend`), then each container is run and asserted:
  the backend container boots against a real `postgres:16` service with the
  compose-equivalent `DATABASE_URL` (via
  `--add-host=host.docker.internal:host-gateway`), so startup runs the Alembic
  migration chain and demo seed *from inside the image* — the exact R-015
  wiring — and `GET /health` must return 200 within the retry window; the
  frontend container must serve the built SPA (`id="root"` in the response
  body). Failures dump `docker logs` before exiting non-zero.
- **Not run locally** — no Docker on the development machine; CI-only per the
  scope doc's exemption. Local gates unchanged (ruff/pytest backend, and the
  frontend gates below from S-05 onward).

**S-04 CI result (run `43048438611` on `8cf3370`, all four jobs green):** both
images built and booted on the first push. Verbatim evidence from the job log
(job databaseId `130618643278`):

```
Docker (build + container smoke test)	Build the backend image	#13 naming to docker.io/library/fairschedule-backend:ci done
Docker (build + container smoke test)	Run the backend container and assert GET /health returns 200	backend container serves GET /health with 200
Docker (build + container smoke test)	Build the frontend image	#17 naming to docker.io/library/fairschedule-frontend:ci done
Docker (build + container smoke test)	Run the frontend container and assert the SPA is served	frontend container serves the built SPA
```

The backend container reaching `/health` 200 also proves the in-image Alembic
migrations plus demo seed ran against the real PostgreSQL service (the R-015
wiring). Run URL:
https://github.com/M-A-E-A/fairschedule-ai/actions/runs/43048438611


### S-05 — 3D campus ↔ schedule integration (commit: this milestone's)

The scene now talks to the timetable instead of being decorative geometry:

- `CampusPage` gained a **day selector** (Monday–Sunday, matching the backend's
  `DAY_NAMES`) and a **time-of-day selector** (default 09:00). Buildings in
  the 3D scene and entries in the legend list are colored by **live occupancy
  for that window**: red (`#f87171`) while a session covers the selected
  (day, time), green (`#34d399`) otherwise. The occupancy window semantics
  (start inclusive, end exclusive) live in the exported pure helper
  `occupiedRoomIds(bookings, day, minute)` — no static or hardcoded
  occupancy anywhere; it recomputes from the bookings payload on every
  selector change.
- **Clicking a room's building (mesh `onClick`) or its legend button** opens a
  schedule panel for that room on the selected day, sorted by start time,
  with course (`code · name`), lecturer, cohort, time range, and status badge;
  an empty state names the room and day when nothing is booked. Selecting
  survives day switches and clears when the campus changes.
- Data comes **only from existing authenticated, tenant-scoped endpoints**:
  `GET /institutions/:id/bookings` (the backend already role-scopes students
  to their own cohort there — students see an explicit "occupancy reflects
  your cohort's sessions" hint), plus `/rooms`, `/campuses`, and the existing
  `/courses`, `/lecturers`, `/student-groups` label lookups. No new backend
  endpoint was needed.
- Tests (`frontend/src/pages/CampusPage.test.tsx`, rewritten): pure-helper
  boundary semantics (start inclusive/end exclusive/other day/empty),
  time parse/format round-trips, occupancy legend text per room, campus
  switching, **recoloring on day/time changes including the mesh material
  color in the scene**, room schedule selection from a legend click
  (including day re-scope), and selection from a 3D mesh click. The
  `@react-three/fiber` `Canvas` mock renders its scene children as DOM, so
  the tests click the actual `mesh[name=…]` nodes and read their
  `meshstandardmaterial` colors — the 3D wiring is under test, not mocked
  away.

Raw local gate output (frontend):

```
$ npm run lint
> fairschedule-ai-frontend@0.1.0 lint
> eslint .

(finishes with 0 errors; 3 pre-existing-style react-refresh warnings for the
exported helper/component pattern the page already used before this round)

$ npm run test -- --run
Test Files  12 passed (12)
     Tests  37 passed (37)
   Duration  43.50s

$ npm run build
✓ built in 4.14s
```

(32 tests before this round − 2 replaced + 7 = 37; the main chunk is still
1,551 kB with the >500 kB warning — three.js — which is exactly S-11's
mandate, not addressed here.)

## Interim failures

(Each push's CI failures, root causes, and fixes are recorded here as they
happen.)
