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
| S-05 | 3D campus ↔ schedule integration | done | `fe90cfe` |
| S-06 | Timetable publish workflow | done | `d2429a0` |
| S-07 | CSV import | done | `29db218` |
| S-08 | ICS calendar export | done | `9778455` |
| S-09 | Audit timeline UI | done | (this commit) |
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

**S-05 CI result (run `43049633451` on `fe90cfe`, all four jobs green):**
https://github.com/M-A-E-A/fairschedule-ai/actions/runs/43049633451

### S-06 — timetable publish workflow (commit: this milestone's)

Draft → published with versioning, plus a draft-vs-published diff, on the
backend and in the timetable page:

- New table `TimetableVersion` (`app/models/tenant.py`): one row per
  published version — per-tenant 1-based `version` (unique per institution),
  `label`, `published_by_email`, wall-clock UTC `published_at`, and an
  immutable `json_payload` snapshot of the tenant's booking rows (fields
  only — no joined labels, because a published version is history and must
  stay meaningful after the referenced rows change or disappear). Alembic
  migration `c4f8a1d2e6b7` (chain is now `72bbb9943009` → `a1c4e7f9d2b3` →
  `c4f8a1d2e6b7`); `alembic/env.py` imports the model for future
  autogeneration.
- `POST /institutions/:id/timetable/publish` — freezes the tenant's current
  bookings as the next named version and records a `timetable_published`
  audit event. RBAC: `PROPOSAL_APPROVERS` (administrator, campus operator)
  — the same human-in-the-loop boundary as proposal approval. Blank label
  falls back to `Version N`.
- `GET /institutions/:id/timetable/versions` — published versions newest
  first (id, version, label, publisher, timestamp, session count); staff
  (`SCHEDULE_MANAGERS`) only, like the timetable itself.
- `GET /institutions/:id/timetable/diff` — added / removed / moved sessions
  between the live draft and the latest published version, keyed by booking
  id (moved = room/day/start/duration change, reported with `from`/`to`).
  Never-published tenants get the honest `published_version: null` with the
  whole draft as added. Both endpoints are tenant-checked.
- Frontend (`TimetablePage`): a "Published versions" panel listing versions,
  a publish form (label + button) shown only to `PROPOSAL_APPROVER_ROLES`
  (faculty see versions and diffs but never a publish button), and a
  draft-vs-published summary with per-session change rows. Publishing
  prepends the new version and refetches the diff.
- Tests: `backend/tests/test_timetable_publish.py` (8) — publish freezes a
  named version with an audit event, default label, staff-only
  versions/diff, approvers-only publish (faculty and student refused),
  cross-tenant publish refused, empty diff right after publishing,
  added/moved/removed each observed and correctly classified (including
  that deleting a session the publish contains stays `removed`), and the
  never-published shape. Frontend: TimetablePage versions+diff rendering
  without a publish button for faculty, and administrator publish flow
  (POST payload asserted, new version prepended, diff refetched) — 2 new
  component tests; the pre-existing tests were updated to stub the two new
  endpoints (the fetch stub matches by substring, so the specific routes
  must be registered before the timetable prefix).

Raw local gate output (backend):

```
$ python -m ruff check .
All checks passed!

$ python -m pytest -q
135 passed, 1 warning in 50.85s
```

(127 after S-04 + 8 new S-06 tests.)

Raw local gate output (frontend):

```
$ npm run lint
> fairschedule-ai-frontend@0.1.0 lint
> eslint .

(0 errors; the same 3 pre-existing react-refresh warnings as before)

$ npm run test -- --run
Test Files  12 passed (12)
     Tests  39 passed (39)

$ npm run build
✓ built in 1.04s
```

(37 after S-05 + 2 new TimetablePage tests.)

While re-verifying the gates before committing, one full-suite run flaked:
`renders the institution timetable for staff` hit the 1 s default of
`findByRole` on a loaded dev machine (jsdom startup was 48% of the run) and
the page was still in its loading state when the query timed out; the same
file passed in isolation and the full suite passed on re-run. To keep shared
CI runners from tripping the same 1 s limit, `setupTests.ts` now sets
`configure({ asyncUtilTimeout: 5000 })` — every `findBy*` still requires
exactly the same element to appear, only the wall-clock allowance changed.


### S-07 — CSV import (commit: this milestone's)

Bulk-loading of institution data, all-or-nothing, with row-level diagnostics:

- New endpoint `POST /institutions/{id}/import/{dataset}` (`app/api/csv_imports.py`)
  for `rooms`, `courses`, `lecturers`, and `student-groups` (the scope's
  minimum of rooms and courses plus the two datasets its motivation names).
  The file arrives as a multipart upload (field `file`) and is parsed with the
  **standard library `csv` module only** — no new dependencies (`python-multipart`
  was already a pinned dependency for FastAPI form handling).
- **All-or-nothing:** every row is validated before a single INSERT; any
  failure raises `400` with `detail.message` ("N row(s) failed validation;
  nothing was imported") and `detail.errors` = *every* failing row as
  `{row, reason}`, where `row` is the physical line number in the file
  (header = row 1, taken from `csv.reader.line_num`). Nothing is added to the
  session on the failure path, so the request's rollback guarantees no
  partial import. Success commits all rows in one transaction plus a
  `csv_import` audit event.
- Row validation per dataset: value types and ranges (`capacity` 1–10000,
  `size` 1–100000), required fields, tenant-owned references (a `campus_id`
  outside the institution is a row error), email syntax for lecturers
  (syntax-only, `check_deliverability=False` — no network calls in
  validation), and duplicates both inside the file and against existing
  tenant rows (room name per campus, course code, lecturer email, group
  name). Missing required header columns are a row-1 error; a header-only
  file is refused; a UTF-8 BOM (Excel) is tolerated; non-UTF-8 input is a
  reported error. Extra columns are ignored; optional columns default to the
  model defaults.
- **Role gating:** `ROOM_MANAGERS` (administrator, campus operator) only —
  faculty and students get 403, unauthenticated 401. **Tenant scoping:**
  `ensure_tenant` refuses another tenant's institution id with `403
  tenant mismatch` before the file is read.
- Documented in the README (feature bullet + a "CSV import" section with the
  per-dataset column table, the security semantics, and a curl example).
- Tests (`backend/tests/test_csv_import.py`, 13): valid rooms file (rows
  created + audit event), valid courses file, a bad-rows file asserting
  **every** error is reported (rows 3/4/5 each with its reason) **and**
  nothing was imported (not even the valid row), duplicate-inside-file,
  missing header column, header-only file, lecturers + student-groups,
  invalid email, cross-tenant rejection (403 + target tenant unchanged),
  faculty/student 403, operator allowed, unauthenticated 401, unknown dataset
  404. A module-scoped teardown deletes every imported row so the exact seeded
  counts other modules assert (e.g. `north['rooms'] == 4`) stay true — import
  tests run before `test_dashboard_ai` alphabetically, and the cleanup makes
  that ordering irrelevant anyway.

Raw local gate output (backend):

```
$ python -m ruff check .
All checks passed!

$ python -m pytest -q
148 passed, 1 warning in 55.37s
```

(135 after S-06 + 13 new S-07 tests; the 1 warning is the known anyio
`BlockingPortal` DeprecationWarning from starlette's TestClient, present
since round 1.)

**S-07 CI result (run `43302265537` on `29db218`, all four jobs green):**
Backend (lint + test) 46s, Frontend (lint + test + build) 25s, Docker (build +
container smoke test) 1m22s, Backend (PostgreSQL 16) 1m19s. Run URL:
https://github.com/M-A-E-A/fairschedule-ai/actions/runs/43302265537

### S-08 — ICS calendar export (commit: this milestone's)

`GET /me/schedule.ics` now serves the caller's own schedule as a downloadable
calendar:

- New module `app/api/calendar.py`. Events are built from
  `build_schedule_payload()` — the function `GET /me/schedule` itself serves,
  extracted from it in this milestone — so the JSON view and the export share
  **one** implementation of the R-007 role scoping (student → cohort, faculty
  → own lectures, staff → institution; unlinked faculty → empty schedule) and
  cannot drift.
- Response is `text/calendar` with
  `Content-Disposition: attachment; filename="schedule.ics"`.
- Structure per RFC 5545: `BEGIN:VCALENDAR` / `VERSION:2.0` / `PRODID` /
  `CALSCALE` / `METHOD:PUBLISH`, a self-contained `VTIMEZONE` for `Etc/UTC`,
  and one `VEVENT` per session with `UID:fairschedule-{booking id}@fairschedule-ai`
  (stable identity derived from the immutable booking id), `DTSTAMP`,
  `SUMMARY`, `DESCRIPTION` (lecturer + cohort), and `LOCATION` (room).
- **Timezone-explicit times:** naive wall-clock booking minutes are anchored
  to Monday of the current UTC week and emitted as
  `DTSTART;TZID=Etc/UTC:YYYYMMDDTHHMMSS` / `DTEND;TZID=…` — never floating
  times — with the matching `VTIMEZONE` block in the same document.
- **RFC 5545 TEXT escaping** (`escape_text`): backslash first, then `;`, `,`
  and newlines → `\n`; **line folding** (`fold`): every physical line is
  ≤ 75 octets with CRLF + space continuations, split on UTF-8 octet
  boundaries so multi-byte characters never break.
- Unauthenticated requests are rejected with 401 through the shared bearer
  dependency (same as `/me/schedule`).
- Tests (`backend/tests/test_ics_export.py`, 10): full structure assertions
  (wrapper, CRLF endings, VTIMEZONE, 3 VEVENTs for the administrator,
  per-event UID/DTSTAMP/TZID-qualified DTSTART/DTEND/SUMMARY, unique UIDs,
  exact Monday date + 09:00/10:30 wall-clock round-trip, 75-octet line-limit
  check), student cohort scoping (2 events, `DBS201` never exported, Tuesday
  anchor), faculty own-lectures scoping (1 event), unlinked faculty → valid
  but empty calendar, operator → whole institution, special-character
  escaping end-to-end (a course named `Physics; I, Part \ Two\nEnd` inserted
  directly then cleaned up in-test), unauthenticated 401, plus unit tests for
  `escape_text`, `fold` (limit + reassembly, ASCII and multi-byte) and
  `week_anchor`. A module-scoped fixture provisions the unlinked-faculty
  account and removes every row the module adds, so no state leaks to later
  modules.

Raw local gate output (backend):

```
$ python -m ruff check .
All checks passed!

$ python -m pytest -q
158 passed, 1 warning in 56.73s
```

(148 after S-07 + 10 new S-08 tests.)

**S-08 CI result:** recorded with the next push's run below once observed.

### S-09 — audit timeline UI (commit: this milestone's)

The admin-only audit endpoint now has an interface:

- New page `frontend/src/pages/AuditPage.tsx` at route `/admin/audit`,
  wrapped in `RequireRole allow={['administrator']}` and listed in the
  AppShell nav (`Audit log`, administrator-only). It renders the existing
  `GET /audit-events` endpoint — no backend changes were needed or made:
  rows are sorted **newest first** client-side by id (so the guarantee holds
  regardless of server ordering), **paginated** 10 per page with
  Previous/Next + `Page X of Y` + a totals line, and **filterable by event
  type** (a `<select>` whose options are derived from the returned events;
  changing the filter resets to page 1, and a stale page number is clamped so
  shrinking result sets can never strand the user on an empty page).
- Columns: `#` (id), event type badge, message, user email. Error state
  surfaces the API failure (`role="alert"`) instead of a fake empty
  timeline; loading uses the shared Lottie loader.
- Tests (`frontend/src/pages/AuditPage.test.tsx`, 5): newest-first ordering
  from an oldest-first payload + full pagination walk (1→2→3, remaining 5
  rows, Next disabled at the end, Previous re-enables), filter
  (`proposal_approved` → 8 of 25, `Page 1 of 1`, non-matching rows gone,
  filter reset from a deep page), **campus operator and student each bounced
  off `/admin/audit` with the `audit-events` fetch provably never issued**
  (fetch stub call inspection), and the error-notice path.
  The backend's own role gate (403 for non-administrators) is already
  covered by `test_rbac.py::test_student_cannot_read_audit_log` /
  `test_operator_cannot_read_audit_log`.

Raw local gate output (frontend):

```
$ npm run lint
> fairschedule-ai-frontend@0.1.0 lint
> eslint .

(0 errors; the same 3 pre-existing react-refresh warnings for
CampusPage.tsx's exported-helper pattern)

$ npm run test -- --run
 Test Files  13 passed (13)
      Tests  44 passed (44)

$ npm run build
✓ built in 6.97s
```

(39 after S-06 + 5 new AuditPage tests; main chunk still 1,557 kB with the
>500 kB warning — S-11's mandate, not this item's.)

## Interim failures

(Each push's CI failures, root causes, and fixes are recorded here as they
happen.)
