# Review ledger

Shared memory for the FairSchedule AI Developer/Reviewer loop. Both agents read and
append to this file every round. It is the authoritative record of what is open, what is
fixed, and what was explicitly deferred — so prior feedback is tracked and never
reintroduced.

Protocol: [`docs/AGENT_PROTOCOL.md`](docs/AGENT_PROTOCOL.md).

## How to use this file

- **Every issue ever raised gets an ID** (`R-001`, `R-002`, …) and a row in the index.
  IDs are stable and unique across rounds and are never reused.
- **Status is one of** `open`, `resolved`, or `deferred`. A `deferred` entry must carry
  the exact justification the Developer gave; "will do later" is not a justification.
- **The Developer appends its handoff entry** and updates the status of each issue it
  addressed, saying how it fixed it.
- **The Reviewer appends its review entry** and independently verifies each prior issue:
  `resolved`, still `open`, or `reintroduced`. An issue that reappears is a new finding
  and is called out as a reintroduction.
- **The loop ends only when the index has zero `open` rows and the Reviewer's latest
  verdict is `APPROVE`.**

## Issue index

| ID | Title | Raised in | Status | Resolution / justification |
|----|-------|-----------|--------|-----------------------------|
| B-001 | Baseline scaffold present before round 1 | baseline | resolved | Superseded by round 1 delivery; retained for provenance only. Not a review finding. |
| R-001 | Proposal approval skips backend revalidation (PROJECT.md) | round 1 (review) | open | `approve_proposal` applies stale solver rows without re-checking hard constraints against current data. |
| R-002 | SSO links existing accounts by email without `email_verified` | round 1 (review) | open | Unverified-email IdP allows takeover of any matching account, including administrators. |
| R-003 | Room capacity/room_type edits don't revalidate existing bookings | round 1 (review) | open | Shrinking a room or changing its type can leave stored bookings violating hard constraints. |
| R-004 | Compose CORS allowlist uses container hostname, not browser origin | round 1 (review) | open | `http://frontend:5173` never matches the browser `Origin`, so Compose API calls fail preflight. |
| R-005 | Compose ships fixed committed JWT secret `change-me` | round 1 (review) | open | Contradicts config design; repo holders can forge tokens for default deployments. |
| R-006 | Unscoped lookups load every tenant's rows per request | round 1 (review) | open | `select(Course/Lecturer/StudentGroup/Room)` without institution filter in dashboard, scheduling, ai. |
| R-007 | `/me/schedule` and AI scope branch on lecturer link, not role | round 1 (review) | open | Contradicts documented scoping; dead branch in `_faculty_context`. |
| R-008 | `POST /ai/chat` accepts untyped dict body | round 1 (review) | open | No Pydantic schema, no OpenAPI validation; inconsistent with the rest of the API. |
| R-009 | Compose stack never executed; frontend container is dev server | round 1 (review) | open | Static verification only; `npm run dev` in the image, no production build. |
| R-010 | `.env.example` documents unread `USE_SQLITE_FOR_TESTS` | round 1 (review) | open | Misleading configuration surface; nothing reads the variable. |
| R-011 | README/login demo docs inaccurate | round 1 (review) | open | Wrong default DB filename; seeded `harbor-admin` tenant undocumented. |
| R-012 | `@react-three/drei` declared but never imported | round 1 (review) | open | Dead dependency inflating install and bundle size. |
| R-013 | Frontend tree reports 18 known vulnerabilities | round 1 (review) | open | Visible in CI `npm ci` (2 critical, 1 high, 15 moderate); no audit gate. |
| R-014 | No rate limiting on login; enumeration timing side channel | round 1 (review) | open | Unlimited guessing plus response-time oracle for account existence. |

## Round log

### Baseline (pre-loop)

Starting state handed to the Developer before round 1: a partial scaffold containing a
FastAPI backend with 6 tests, a React/Vite frontend with 1 test, a GitHub Actions
workflow, `docker-compose.yml`, and this ledger. Known gaps at baseline included no lint
tooling anywhere, no Alembic migrations, no backend role enforcement, an unauthenticated
tenant-leaking endpoint, a stubbed SSO path, and no `frontend/Dockerfile` despite
`docker-compose.yml` declaring `build: ./frontend`.

### Round 1

- **Developer:** delivered `da9af1f85b9a02af5dd6814d4908be57c5dff397` (handoff:
  [`docs/rounds/round-01-handoff.md`](docs/rounds/round-01-handoff.md)).
  - Backend green: 204 `DELETE`s return explicit `Response(status_code=204)`
    (with `from __future__ import annotations`, `-> None` resolves to
    `NoneType`, which FastAPI treats as a required body); B008 resolved via
    `extend-immutable-calls` in `backend/ruff.toml` — FastAPI's
    `Depends()`/`Security()` argument defaults are the framework's documented
    DI idiom, evaluated once at route definition, so restructuring would only
    destroy dependency composition/OpenAPI docs for no safety gain (reasoning
    in the handoff); missing `import sqlmodel` added to the initial Alembic
    migration; 13 broken tests fixed by correcting test code, never by
    weakening assertions. `python -m pytest -q` → **96 passed**;
    `python -m ruff check .` → **All checks passed!**
  - Frontend built out: username **and** email sign-in (tab toggle, correct
    request bodies, SSO config button, `#access_token=` handling), role-aware
    routing/views for administrator, campus operator, faculty/scheduler and
    student via `AuthProvider` + `RequireRole` + role-filtered `AppShell` nav,
    student "my schedule" backed by `GET /me/schedule`, plus Dashboard,
    Timetable, Rooms, AdminUsers, AI and R3F Campus pages. Stack verified in
    use at import level: React Router, GSAP + ScrollTrigger, **Lottie**
    (`lottie-react` loader, previously unused, now the loading state of seven
    pages with its own tests), React Three Fiber, and the CSS component
    system. Tests went 1 → **31 across 12 suites**, covering the
    security-relevant paths (route guards, role navigation, both login
    methods, student scoping). `npm run lint` clean,
    `npm run test -- --run` → **31 passed**, `npm run build` → success with
    asset hashes identical to CI.
  - `frontend/Dockerfile` added to match compose's `build: ./frontend`
    (node:20-alpine, `npm ci`, port 5173, `--host 0.0.0.0`), with
    `.dockerignore`. README updated: Alembic commands, both lint commands,
    both login methods with verified demo usernames/emails.
  - **Local/CI mismatch found and fixed**: first push (run `42778091742`)
    failed CI with 80 errors + 5 login failures because unpinned `bcrypt` 5.x
    is incompatible with `passlib[bcrypt]==1.7.4` (removed `__about__`,
    `UnknownHashError` on verify); local had 4.0.1, CI got 5.0.0. Pinned
    `bcrypt==4.0.1` and reproduced both halves in a fresh venv. CI run
    `42779053236` on `da9af1f` is fully green and matches local exactly.
  - **Docker was never executed** — not installed on this machine;
    `docker-compose.yml` was verified statically only (existence of both
    Dockerfiles, `build: ./frontend`, port/`VITE_API_BASE_URL` wiring, YAML
    parse). No push blocker occurred; the workflow file was not modified.
- **Reviewer:** audited `8bf412b83a7c4f655b31c68d66b8b7475933eca4` statically — every tracked
  file — plus the full CI log of run `42780593038` (which checked out this exact SHA). All
  checks pass and local/CI agree exactly (96 backend tests, Ruff clean, 12 files/31
  frontend tests, build green with identical asset hashes), so there are **no blocking
  issues**; verdict is **REJECT** with 14 open findings (R-001 … R-014), the most
  substantial being: proposal approval skipping the backend revalidation PROJECT.md
  requires (R-001), SSO account linking on unverified emails (R-002), room edits that
  can break stored bookings' hard constraints (R-003), and a Compose stack whose CORS
  allowlist and dev-server frontend mean it has never actually worked (R-004, R-009).
  Prior issue B-001 verified resolved. Full detail:
  [`docs/rounds/round-01-review.md`](docs/rounds/round-01-review.md).
