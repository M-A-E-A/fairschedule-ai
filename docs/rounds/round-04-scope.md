# Round 4 scope — approved extension

Approved by the project owner on 2026-11-11. Items **S-01 through S-13** are mandatory
requirements for round 4, alongside everything already resolved in `ISSUES.md`
(`R-001`–`R-015` must remain fixed — none may be reintroduced).

Scope items are referenced by `S-NN` so they never collide with review finding IDs
(`R-NNN`, which continue from `R-016`).

## CI-only verification jobs

Docker, Redis, and a local PostgreSQL server are **not available on the development
machine**. Two scope items (`S-03`, `S-04`) therefore add CI jobs that can only execute
on GitHub's runners. These jobs are **exempt from the local/CI symmetry requirement by
design** — that is their purpose: to execute what the local environment cannot. Every
other check must still pass identically locally and in CI. The blocking rule's
"local and CI disagree" condition applies to checks that can run in both environments.

## Tier 1 — close the gap between green checks and a working system

### S-01 — Solver time limit

`backend/app/services/scheduler.py` never sets `solver.parameters.max_time_in_seconds`.
A large institution can hang the request and pin a worker.

- Set a wall-clock limit (default 10s, configurable via an env var documented in
  `.env.example` and the README).
- Handle non-optimal outcomes honestly: report solver status including `UNKNOWN`
  (timeout), never present a partial result as a full schedule, and never crash.
- `docs/PROJECT.md` already lists "time to generate" and "timeout" as evaluation
  metrics — the response should expose the solve time and status.

**Acceptance:** unit tests covering (a) a solvable instance within the limit, (b) status
reporting on an artificially tiny limit where the solver cannot finish, (c) env-var
override.

### S-02 — Rate limiter persistence

`backend/app/services/rate_limit.py` stores failures in an in-process `defaultdict`.
Multiple uvicorn workers or replicas each keep their own counter, multiplying the
effective lockout threshold.

- Replace the in-memory store with a persistent store the app already has (a database
  table via SQLModel + Alembic migration), keeping the sliding-window semantics,
  identical unknown/known-account behavior, and timing equalization from `R-014`.
- Expired attempts must be pruned so the table cannot grow unboundedly.

**Acceptance:** tests proving the lockout survives the store being recreated (the
actual defect class: fresh process, existing failures still enforced), plus the existing
`R-014` throttle tests still passing unchanged.

### S-03 — PostgreSQL exercised in CI

Tests run only on SQLite; the Alembic migrations target PostgreSQL but have never run
against a real Postgres anywhere.

- Add a CI job with a `postgres:16` service container: run `alembic upgrade head`
  against it, then run the backend test suite with `DATABASE_URL` pointed at it.
- The local default (SQLite) must remain unchanged and the existing workflow untouched.
  `tests/conftest.py` must respect an explicit `DATABASE_URL` instead of forcing SQLite
  unconditionally.

**Acceptance:** green CI run of the Postgres job; any dialect-specific failures found
and fixed (that is the point of the job). This job is CI-only per the exemption above.

### S-04 — Docker build + container smoke test in CI

The images have never been built or run anywhere (the standing deferral in `R-009`/`R-015`).

- Add a CI-only job that builds both images (`backend`, `frontend`) with
  `docker build`, then smoke-tests them: run the backend container and assert
  `GET /health` returns 200; run the frontend container and assert its HTTP root
  serves the built SPA.

**Acceptance:** green CI run proving both images build and boot. This closes the
standing "never executed anywhere" disclosure. CI-only per the exemption above.

## Tier 2 — product depth

### S-05 — 3D campus ↔ schedule integration

`frontend/src/pages/CampusPage.tsx` fetches real campuses and rooms, but the scene does
not talk to the timetable.

- Add a day/time selector; color buildings and rooms by live occupancy for that window.
- Clicking a room (or its building) shows that room's schedule for the selected day.
- Data comes from existing authenticated, tenant-scoped endpoints — add endpoints only
  if genuinely needed, and any new endpoint is tenant-scoped and role-gated like the rest.

**Acceptance:** component tests with mocked data covering occupancy coloring and
selection; no static/hardcoded occupancy.

### S-06 — Timetable publish workflow

Bookings have `status='draft'` and proposals an approval path, but no publish lifecycle.

- Implement draft → published with versioning: publishing freezes a named version of
  the institution's timetable; the previous version remains queryable.
- Provide a diff between the current draft and the currently published version
  (added / removed / moved sessions).

**Acceptance:** API tests for publish, version listing, and diff correctness (including
an empty-diff case); RBAC — only roles permitted to publish may do so; audit events
recorded.

### S-07 — CSV import for institution data

Nobody types a university's courses, rooms, lecturers, and student groups by hand.

- Admin/operator-facing import endpoint (stdlib `csv`; no new dependencies) for at least
  rooms and courses, with per-row validation errors returned (row number + reason), and
  all-or-nothing semantics (a bad row imports nothing).
- Tenant-scoped and role-gated; documented in the README.

**Acceptance:** tests with a valid file, a file with bad rows (asserting nothing
imported and every error reported), and cross-tenant rejection.

### S-08 — ICS calendar export

No calendar export exists today.

- `GET /me/schedule.ics` returning `text/calendar` for the requesting user's own
  schedule (student → cohort, faculty → own lectures, per the `R-007` scoping rules).
- Correct ICS structure: `BEGIN:VCALENDAR`/`END:VCALENDAR`, `VEVENT` per session with
  `UID`, `DTSTART`/`DTEND` (timezone-explicit), `SUMMARY`, and proper escaping.

**Acceptance:** tests asserting structure, escaping of special characters, and role
scoping; unauthenticated access rejected.

### S-09 — Audit timeline UI

`GET /audit-events` exists (admin-only) but has no interface.

- Admin page rendering the audit timeline, newest first, with pagination and at least
  one filter (event type or user), driven by the existing endpoint.

**Acceptance:** component tests with mocked data; non-admins cannot reach the page or
the data.

### S-10 — Solver metrics dashboard

`docs/PROJECT.md` specifies evaluation metrics (hard violations, soft preference
matches, undesirable slots, generation time, repair changes, solver status) with no
reporting surface.

- The schedule-generation response exposes a metrics block populated with those values.
- A frontend panel on the scheduling page renders them.

**Acceptance:** backend tests asserting the metrics block's fields and values against a
known fixture; component test for the panel.

## Tier 3 — engineering polish

### S-11 — Route-level code splitting

`React.lazy` is used nowhere; three.js sits in the main bundle (the >500 kB chunk
warning has existed since baseline).

- Lazy-load the 3D campus view (and any other heavy, non-landing route) behind
  `Suspense`, so the initial bundle shrinks measurably.

**Acceptance:** the main chunk drops below the warning threshold or the split is
otherwise measurable in build output; all existing tests still pass (lazy components
render under `Suspense` in tests).

### S-12 — Playwright end-to-end smoke tests

Current coverage is unit/component only; auth and RBAC flows across the real UI are
untested.

- Add Playwright with a small smoke suite: sign in as an admin (username/password),
  reach the dashboard; sign in as a student, verify role-appropriate behavior (e.g. the
  student schedule view, and an admin-only page being unreachable).
- Runs against the real backend and the built frontend, wired as a CI job.
- Attempt this in good faith. If genuinely blocked (CI runner limits, browser
  installation), state exactly why with evidence and implement the smallest viable
  alternative — silent skipping is not permitted.

**Acceptance:** green E2E run in CI covering both role paths.

### S-13 — Coverage and mypy gates

Neither exists.

- Add `pytest-cov` with a coverage threshold in CI. The threshold must be set at or
  below the *measured current* coverage (gate against regressions, not an aspiration).
- Add `mypy` for the backend, config in `pyproject.toml` or `mypy.ini`, type errors
  fixed rather than silenced, and a CI gate.

**Acceptance:** both gates green in CI; the chosen coverage threshold documented with
the measured value that justified it.

## Non-goals for round 4

- No new external services in local development (Redis, message queues) — S-02 must use
  the database the app already has.
- No changes to the resolved findings `R-001`–`R-015` other than what these items
  require; none may be reintroduced.
- The protocol, prompts, and prior round artifacts are not modifiable by the agents;
  concerns go in `ISSUES.md`.
