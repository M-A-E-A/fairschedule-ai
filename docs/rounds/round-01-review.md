# Round 1 — Reviewer report

- **Audited snapshot:** `8bf412b83a7c4f655b31c68d66b8b7475933eca4` (handoff commit; code identical to
  `da9af1f85b9a02af5dd6814d4908be57c5dff397` — the only delta is this round's handoff and ledger docs).
- **Scope:** every tracked file in the `git ls-files` manifest (98 files), read statically. No tests,
  lint, builds, installs, or servers were run by the Reviewer.
- **CI verification:** GitHub Actions run `42780593038` checked out `8bf412b83a7c…` directly (fetch ref
  and `git log -1` in the log confirm the audited SHA). Backend job: `ruff check .` → "All checks
  passed!", `pytest -q` → **96 passed** (2 deprecation warnings). Frontend job: `eslint .` clean,
  `vitest run` → **12 files / 31 tests passed**, `tsc -b && vite build` → success with
  `dist/assets/index-Cm1cZIql.css` and `dist/assets/index-8GKjyoxf.js` — the same asset hashes the
  handoff reports for local runs. The handoff's pasted raw output and full CI log match this run's
  results; the pasted log is from run `42779053236` (same code, `da9af1f`), which is superseded by the
  green `8bf412b` run verified here.

## 1. Verdict

**REJECT** — zero blocking issues (every check passes locally and in CI, and the two agree), but 14
findings remain open, listed below. Per protocol, `APPROVE` requires zero remaining issues.

## 2. Blocking issues

None. All required checks pass on the audited commit, local and CI outputs agree exactly, and the
CI log corresponds to the pushed snapshot.

## 3. Findings

### R-001 — Proposal approval skips the backend revalidation required by PROJECT.md

- **Location:** `backend/app/api/scheduling.py`, `approve_proposal` (lines 142–180).
- **Problem:** Approval applies the proposal's stored rows straight onto `SessionBooking`
  (`room_id`, `day`, `start_minute`, `status='published'`) without re-running any hard-constraint
  check. The rows were validated only at generation time, by the solver, against the data as it
  existed then. `docs/PROJECT.md` (line 23) requires: "Any proposed change must be validated again
  by the backend before approval and audit logging."
- **Consequence:** Between generation and approval, bookings can be created, edited, or deleted via
  the bookings API and rooms can shrink or change type. A stale proposal then silently overwrites
  those concurrent edits and publishes sessions that double-book a room, lecturer, or cohort, or
  exceed room capacity — the exact states write-time enforcement in `bookings.py` exists to prevent.
  The audit log records "approved" for a timetable that can be in violation of the hard
  constraints.
- **Fix:** On approve, load the tenant's current bookings, reconstruct the post-application state,
  and run `count_hard_violations` / the `_validate_hard_constraints` rules against it (also checking
  each `room_id` still exists on the proposal's campus). Reject with `409` if any violation or stale
  reference is found; only then apply rows and write the audit event.

### R-002 — SSO auto-links existing accounts by email without checking `email_verified`

- **Location:** `backend/app/services/sso.py`, `exchange_code_for_identity` (lines 101–111), and
  `backend/app/api/auth.py`, `_resolve_sso_user` (lines 138–145).
- **Problem:** The identity claims are used without inspecting the `email_verified` claim, and
  `_resolve_sso_user` then attaches `external_subject` to *any* existing account whose email matches
  — including administrators ("Existing account (any role) opts into SSO by signing in once").
- **Consequence:** With the supported `oidc` provider mode pointing at an identity provider that
  returns unverified emails, an attacker who controls an unverified address matching an
  administrator's email signs in via SSO once and permanently links (and therefore authenticates as)
  that administrator. This is the classic OIDC account-takeover via unverified-email linking.
- **Fix:** Read `email_verified` from the userinfo response and refuse to link to an existing
  account when it is not `true` (return 403 "email not verified by provider"); provisioning of brand
  new accounts may keep the current behavior, or apply the same check.

### R-003 — Room capacity and room-type edits never revalidate existing bookings

- **Location:** `backend/app/api/rooms.py`, `update_room` (lines 76–96).
- **Problem:** `PATCH /rooms/{id}` validates only that a changed `campus_id` belongs to the
  institution. Reducing `capacity` below a cohort's size, or changing `room_type` away from a
  course's requirement, is accepted without checking the bookings that reference the room.
- **Consequence:** The capacity and room-type hard constraints are enforced at booking-write time
  but can be broken afterwards through the rooms API: published sessions remain in the database
  violating constraints the solver and `bookings.py` guarantee elsewhere, and the invariant
  "violations never reach the database" stated in `bookings.py`'s module docstring is lost.
- **Fix:** On capacity/room_type changes, load the room's bookings and reject with `409` if any
  booking's group size exceeds the new capacity or its course requires a different room type (or
  mark those bookings `draft` and say so in the response).

### R-004 — Compose CORS allowlist uses the container hostname, not the browser origin

- **Location:** `docker-compose.yml`, line 22 (`BACKEND_CORS_ORIGINS: http://frontend:5173`).
- **Problem:** The frontend publishes port `5173` to the host and `VITE_API_BASE_URL` points browsers
  at `http://localhost:8000`. The browser's `Origin` header on those cross-origin API calls is
  `http://localhost:5173`, which is not in the allowlist — `http://frontend:5173` is a name only
  resolvable inside the Docker network, never sent by a browser.
- **Consequence:** Every authenticated API request (they all carry the `Authorization` header, so
  they preflight) is rejected by the CORS middleware. `docker compose up` yields a frontend that
  cannot reach its backend, so the Compose stack has never actually worked end to end.
- **Fix:** Set `BACKEND_CORS_ORIGINS: http://localhost:5173` in `docker-compose.yml` (or include both
  origins), and once Docker is available, run the stack once to verify.

### R-005 — Compose ships a fixed, committed JWT secret

- **Location:** `docker-compose.yml`, line 21 (`JWT_SECRET: change-me`).
- **Problem:** A literal secret is committed to the repository, while `backend/app/core/config.py`
  (lines 45–53) was explicitly designed so that no secret ships in the repo — an ephemeral
  per-process secret is generated when `APP_ENV` is not `production`.
- **Consequence:** Anyone with the public repository can forge valid JWTs for any deployment that
  runs the committed Compose defaults, defeating authentication entirely on those deployments.
- **Fix:** Remove the `JWT_SECRET` line and let the existing ephemeral-dev-secret path apply (or
  inject it via an untracked env file / secrets mechanism when it must be stable across workers).

### R-006 — Per-request lookups load every tenant's rows without an institution filter

- **Location:** `backend/app/api/dashboard.py` lines 165–168 and 196–199; `backend/app/api/scheduling.py`
  lines 52–53; `backend/app/api/ai.py` lines 46–47 and 73.
- **Problem:** `select(Course)`, `select(Lecturer)`, `select(StudentGroup)`, `select(Room)` are
  executed unscoped, building id-keyed dictionaries from all institutions' rows, then used to label
  tenant-filtered bookings.
- **Consequence:** No cross-tenant data reaches responses today (IDs are globally unique and the
  booking lists are already tenant-scoped), but each such request loads and materializes every
  tenant's table — cost grows linearly with total tenant data, hurting every list/schedule view —
  and the pattern drops the defense-in-depth (scoped query + `ensure_tenant`) that the rest of the
  backend consistently applies. A future edit that keys these dicts by a non-unique field (e.g.
  `code`) would leak names across tenants.
- **Fix:** Add `.where(Model.institution_id == institution_id)` to every one of these lookups.

### R-007 — `/me/schedule` and AI context branch on the lecturer link, not on role, contradicting the documented scoping

- **Location:** `backend/app/api/dashboard.py`, `my_schedule` (lines 150–163);
  `backend/app/api/ai.py` context selection (lines 116–121) with the now-dead check in
  `_faculty_context` (lines 63–64).
- **Problem:** The docstring promises "faculty their teaching, campus operators and administrators
  the whole institution", but the code branches on `lecturer_id is not None` after the student
  check: an administrator with a lecturer link gets `scope: 'lecturer'` (only their own teaching),
  while a faculty user with no lecturer link falls into the `else` and gets the entire institution's
  schedule. The AI endpoint has the same precedence, so an unlinked faculty user receives the
  staff-level institution overview; `_faculty_context`'s own `lecturer_id is None` branch is
  unreachable.
- **Consequence:** Surprising, undocumented data scoping for mixed role/link accounts, and two
  endpoints disagree with their own docstrings. It is not an escalation (staff can already read the
  institution timetable), but the views are inconsistent and the dead branch misleads future
  maintainers.
- **Fix:** Branch on role first: student → cohort (or explicit empty), faculty → lecturer-scoped
  with an explicit "no lecturer link" answer when unlinked, campus_operator/administrator →
  institution scope. Remove the duplicated `lecturer_id` guard from `_faculty_context`.

### R-008 — `POST /ai/chat` accepts an untyped dict instead of a Pydantic model

- **Location:** `backend/app/api/ai.py`, `ai_chat` (lines 106–114).
- **Problem:** Every other endpoint validates input through `app/schemas`; this one declares
  `payload: dict[str, Any]` and hand-rolls `payload.get('prompt')`.
- **Consequence:** The request body is absent from OpenAPI validation and docs, the hand-written
  "prompt required" 400 replaces schema-driven 422s, and any future field added to the chat payload
  would be silently ignored rather than validated — an inconsistent API contract.
- **Fix:** Add `AiChatRequest(BaseModel)` with `prompt: str` (min length 1) in `app/schemas/` and use
  it as the parameter type.

### R-009 — Compose stack is statically verified only, and the frontend container is a dev server

- **Location:** `frontend/Dockerfile` (line 18, `CMD ["npm", "run", "dev", …]`); handoff section
  "Docker was never executed".
- **Problem:** The Compose stack requirement was verified by reading YAML and checking Dockerfiles
  exist — never run — and the frontend image runs the Vite dev server rather than a production
  build. Combined with R-004, the stack cannot work today.
- **Consequence:** "Docker Compose orchestrates the full stack" is untested claims, not shipped
  behavior; R-004 shows exactly the class of wiring bug that only an execution would have caught.
- **Fix:** Once Docker is available, run `docker compose up --build` and fix what surfaces; build the
  frontend image as a production bundle (multi-stage `npm run build` + static server), or document
  explicitly in the README that Compose is a development-only convenience.

### R-010 — `.env.example` documents `USE_SQLITE_FOR_TESTS`, which nothing reads

- **Location:** `.env.example`, line 5.
- **Problem:** No occurrence of `USE_SQLITE_FOR_TESTS` exists in the backend (config, code, tests,
  or CI); test databases are configured in the test suite itself.
- **Consequence:** A contributor setting it expects behavior that does not exist — a misleading
  configuration surface.
- **Fix:** Delete the line, or implement it where tests decide their `DATABASE_URL`.

### R-011 — README and login-page demo docs are inaccurate

- **Location:** `README.md` line 34 (default DB file) and lines 53–63 (demo credentials);
  `frontend/src/pages/LoginPage.tsx` line 132.
- **Problem:** (a) The README says `DATABASE_URL` "defaults to SQLite (`fairschedule.db`)" but
  `config.py`'s default is `sqlite:///./demo.db`. (b) The seeded second-tenant account
  `harbor-admin` / `demo-admin-harbor` (Harbor College, `backend/app/seed.py` lines 135–139) is
  documented nowhere — neither README nor the login-page hint, which lists only the four
  Northbridge usernames.
- **Consequence:** Setup instructions don't match observed behavior, and the multi-tenant demo —
  the product's headline isolation property — is undiscoverable from the shipped documentation.
- **Fix:** Correct the default filename, and document `harbor-admin` (with its Harbor College
  tenant context) in the README and the login-page demo hint.

### R-012 — `@react-three/drei` is declared but never imported

- **Location:** `frontend/package.json`, line 13.
- **Problem:** `CampusPage.tsx` uses only `@react-three/fiber` primitives (`Canvas`, `mesh`,
  `boxGeometry`, `meshStandardMaterial`); no file in `frontend/src` imports from `drei`.
- **Consequence:** A dead dependency inflating install size and the 1.57 MB bundle; it also drags in
  `three-mesh-bvh`, whose deprecation warning appears in the CI log.
- **Fix:** Remove it from `package.json` and regenerate `package-lock.json`.

### R-013 — Frontend dependency tree reports 18 known vulnerabilities

- **Location:** CI run `42780593038`, frontend job, `npm ci` step: "18 vulnerabilities (15 moderate,
  1 high, 2 critical)".
- **Problem:** The installed frontend tree contains known-vulnerable packages (transitive, in the
  vite/esbuild/three ecosystem per the accompanying warnings). It does not fail the job, so nothing
  currently forces a response.
- **Consequence:** Known-vulnerable code ships in every build; the count also signals that no
  `npm audit` gate exists to catch regressions.
- **Fix:** Run `npm audit`, triage and bump/override the offending transitive dependencies, and
  consider an audit step (e.g. `npm audit --audit-level=high`) in CI.

### R-014 — Login has no brute-force protection and a username-enumeration timing side channel

- **Location:** `backend/app/api/auth.py`, `login` (lines 37–48).
- **Problem:** There is no rate limiting or lockout on `POST /auth/login`, and the condition
  `user is None or not user.password_hash or not verify_password(...)` short-circuits: an unknown
  username returns 401 immediately, while a known one pays the bcrypt cost.
- **Consequence:** Unlimited online password guessing, and a response-time oracle that reveals
  which usernames/emails exist per tenant.
- **Fix:** Equalize timing by running a dummy `verify_password` against a fixed dummy hash when the
  user is not found, and add per-account/IP throttling (middleware or dependency) — or record in the
  README that hardening is deliberately out of demo scope, if that is the intent.

## 4. Prior-issue verification

- **B-001 (baseline scaffold):** resolved — round 1 replaced the scaffold with the full delivery
  (lint tooling present, Alembic migration present, `require_roles`/`ensure_tenant` enforce roles
  and tenant scope, `/demo/tenant-summary` is administrator-only and tenant-scoped, SSO fully
  implemented, `frontend/Dockerfile` exists). Not reintroduced.

## 5. Sound areas

- The OR-Tools CP-SAT engine (`backend/app/services/scheduler.py`) models all required hard
  constraints — room/lecturer/group no-overlap, capacity, room type, availability window, duration —
  with soft objectives including squared fairness terms, a greedy warm start/fallback, and an
  independent violation counter that re-checks its own output.
- Booking create/update enforce room, lecturer, cohort, capacity, and room-type constraints at write
  time, so direct API mutations cannot create conflicts.
- Tenant isolation is consistently enforced: `ensure_tenant` plus role dependencies guard every
  institution-scoped route, and admin user management refuses cross-tenant ids with identical 403s.
- Both required auth methods work for every role — username or email plus password, and a full
  Google/OIDC code flow with signed state, callback handling, and provisioning that never mints a
  privileged role.
- JWT handling is sound: HS256 with expiry, user/role/institution claims, ephemeral dev secret, and
  a hard requirement for `JWT_SECRET` when `APP_ENV=production`.
- Frontend routing is genuinely role-aware: `RequireRole` guards and the `AppShell` navigation match
  the backend's role sets, and the stack is used, not declared — React Router, GSAP + ScrollTrigger
  on the landing page, Lottie loaders with accessible labels, React Three Fiber campus view, and a
  real CSS component system.
- CI runs both backend and frontend jobs; the audited commit's run is green and matches the local
  results byte-for-byte (same test counts, same asset hashes).
