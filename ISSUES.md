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
| R-001 | Proposal approval skips backend revalidation (PROJECT.md) | round 1 (review) | resolved | `approve_proposal` now revalidates: stale-reference checks (session/room deleted or moved off campus) plus full post-application state reconstruction and `count_hard_violations` re-run; `409` + audited `proposal_rejected`; 5 regression tests (`2862470`). |
| R-002 | SSO links existing accounts by email without `email_verified` | round 1 (review) | resolved | `exchange_code_for_identity` surfaces `email_verified`; linking to an existing account and provisioning both require it (`403 email not verified by provider`); subject-matched links unaffected; 4 tests (`867a848`). |
| R-003 | Room capacity/room_type edits don't revalidate existing bookings | round 1 (review) | resolved | `_validate_room_change` rejects `409` when a capacity shrink, room-type change, or campus move would break a referencing booking; documented reject policy; regression test (`3db21fc`). |
| R-004 | Compose CORS allowlist uses container hostname, not browser origin | round 1 (review) | resolved | `BACKEND_CORS_ORIGINS: http://localhost:5173` — the browser origin (`64a60ed`). Stack still never executed; Docker not installed on this machine. |
| R-005 | Compose ships fixed committed JWT secret `change-me` | round 1 (review) | resolved | `JWT_SECRET` line removed from Compose; ephemeral per-process dev secret path applies (`64a60ed`). |
| R-006 | Unscoped lookups load every tenant's rows per request | round 1 (review) | resolved | every Course/Lecturer/StudentGroup/Room lookup in dashboard, scheduling, and ai is institution-filtered (`95deee0`). |
| R-007 | `/me/schedule` and AI scope branch on lecturer link, not role | round 1 (review) | resolved | both branch on role first (student → cohort, faculty → lecturer with explicit unlinked note, operator/admin → institution); dead branch removed from `_faculty_context` (`95deee0`). |
| R-008 | `POST /ai/chat` accepts untyped dict body | round 1 (review) | resolved | `AiChatRequest` schema (prompt 1–2000 chars, blank rejected); schema-driven 422s (`95deee0`). |
| R-009 | Compose stack never executed; frontend container is dev server | round 1 (review) | resolved | frontend image is a production multi-stage build (`npm ci` + `npm run build`, nginx on 5173, SPA fallback `nginx.conf`), `VITE_API_BASE_URL` passed as build arg (`64a60ed`). Execution still not performed — Docker is not installed on this machine; static verification only. |
| R-010 | `.env.example` documents unread `USE_SQLITE_FOR_TESTS` | round 1 (review) | resolved | line deleted (`64a60ed`). |
| R-011 | README/login demo docs inaccurate | round 1 (review) | resolved | default DB corrected to `sqlite:///./demo.db`; `harbor-admin` / `demo-admin-harbor` (Harbor College) documented in README and login-page hint (`64a60ed`). |
| R-012 | `@react-three/drei` declared but never imported | round 1 (review) | resolved | removed from `package.json` and lockfile; no source imports existed; three-mesh-bvh deprecation warning gone from CI (`f413d85`). |
| R-013 | Frontend tree reports 18 known vulnerabilities | round 1 (review) | resolved | toolchain upgraded (router 7, vite 8, vitest 5, plugin-react 5, `@types/three`), lockfile regenerated; `minimatch` pinned to patched `^11.0.5` via override (npm's suggested fix is a breaking eslint downgrade; without the override GHSA-g3hv-75wg-m249 resurfaces); `npm audit` = 0 vulnerabilities (was 18); `npm audit --audit-level=high` added as a CI gate (`f413d85`, `b735b90`). |
| R-014 | No rate limiting on login; enumeration timing side channel | round 1 (review) | resolved | dummy-hash bcrypt verification equalizes every 401; sliding-window per-(IP, identifier) lockout — 5 failures / 15 min → `429` + `Retry-After`, identical for unknown accounts; success resets; 6 tests (`2394eb6`). |
| R-015 | Backend image missing `alembic.ini`/`alembic/` — boots only under Compose's bind mount | round 2 (review) | open | Found by round-2 review: `backend/Dockerfile` copies only `requirements.txt` and `app/`, but startup runs `run_migrations()`, which needs `BACKEND_ROOT/alembic.ini` and `BACKEND_ROOT/alembic`. Works under Compose only because `./backend:/app` is bind-mounted over the image. Fix: add `COPY alembic.ini ./` and `COPY alembic ./alembic` to `backend/Dockerfile` (both already in the build context; `.dockerignore` does not exclude them). |

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

### Round 2

- **Developer:** delivered `b735b9018ed9218e646ac4d1ff295535523bbe8b` (handoff:
  [`docs/rounds/round-02-handoff.md`](docs/rounds/round-02-handoff.md)) — all 14
  findings from the round-1 review implemented; none deferred except the
  execution of the Compose stack, which is impossible on this machine (Docker is
  not installed).
  - **R-001** (`2862470`): `approve_proposal` revalidates the stored solver rows
    against the tenant's *current* data — stale-reference checks (session or room
    deleted / moved off the proposal's campus) plus a reconstruction of the
    post-application state and a full `count_hard_violations` re-run; violations
    reject with `409` and an audited `proposal_rejected` event. Generation params
    travel in the proposal payload so the availability window is rechecked. 5
    regression tests, each proven to fail with the revalidation call disabled.
  - **R-002** (`867a848`): the OIDC `email_verified` claim is surfaced by
    `exchange_code_for_identity` and enforced by `_resolve_sso_user` — linking to an
    existing account (any role) and provisioning both refuse with
    `403 email not verified by provider` unless the provider asserts the address is
    verified; already-linked subject identities are unaffected. 4 new tests,
    endpoint-level tests proven to fail with the gate forced true.
  - **R-003** (`3db21fc`): `update_room` revalidates capacity / room_type / campus
    changes against every booking referencing the room and rejects `409` naming the
    offending booking — documented policy: the operator moves those sessions first.
    Regression test proven to fail with the validation skipped.
  - **R-006/R-007/R-008** (`95deee0`): all dashboard/scheduling/ai lookups
    institution-scoped; `/me/schedule` and AI context branch on role first with an
    explicit note for unlinked faculty and institution scope for operators/admins
    (dead `_faculty_context` branch removed); `POST /ai/chat` takes the
    `AiChatRequest` Pydantic schema (blank/oversized prompts → 422).
  - **R-014** (`2394eb6`): every 401 pays exactly one bcrypt verification (dummy
    hash when no user/no stored hash), and a sliding-window limiter locks out
    5 failed attempts per (client IP, attempted identifier) in 15 minutes with
    `429` + `Retry-After` — equally for nonexistent accounts, so neither timing nor
    lockout leaks account existence. 6 tests.
  - **R-004/R-005/R-009/R-010/R-011** (`64a60ed`): Compose CORS origin is the
    browser origin `http://localhost:5173`; the committed `JWT_SECRET` is gone
    (ephemeral dev secret applies); the frontend image is a production multi-stage
    build served by nginx on 5173 with SPA fallback and `VITE_API_BASE_URL` as a
    build arg; `USE_SQLITE_FOR_TESTS` deleted from `.env.example`; README default
    DB corrected and `harbor-admin` documented. **Docker was still never executed**
    — not installed on this machine; the stack changes are statically verified
    only.
  - **R-012/R-013** (`f413d85`, `b735b90`): completed the inherited uncommitted
    dependency overhaul (the lockfile was missing the `@types/three` tree, so
    `npm ci` failed — regenerated, then verified with a clean `npm ci`):
    `@react-three/drei` removed (never imported), react-router-dom 6→7,
    vite 5→8, vitest 2→5, @vitejs/plugin-react 4→5. `npm audit` now reports **0
    vulnerabilities** (CI reported 18 in round 1); the `minimatch@^11.0.5`
    override is load-bearing (without it GHSA-g3hv-75wg-m249 resurfaces through
    eslint 10 / typescript-eslint 8.72; npm's own fix is a breaking eslint
    downgrade). `npm audit --audit-level=high` added as a CI gate after `npm ci`.
  - **Local/CI mismatch found and fixed**: first push of the round (`f413d85`, run
    `42934118803`) failed the frontend Build step — `@vitejs/plugin-react` v5
    types resolve through the package `exports` map, unreadable under the legacy
    `moduleResolution: "Node"`; local builds had passed only via a stale
    `tsconfig.node.tsbuildinfo` incremental cache skipping `vite.config.ts`.
    `b735b90` sets `moduleResolution: "bundler"` in both tsconfigs; fix verified
    from a clean state (caches deleted, gates re-run). CI run `42934586787` on
    `b735b90` is fully green and matches local exactly: Ruff clean, pytest
    **113 passed**, ESLint clean, Vitest **12 files / 32 tests**, audit
    **0 vulnerabilities**, build with identical asset hashes
    (`index-SvLVliAF.css`, `index-BrSS0O_p.js`).
- **Reviewer:** audited `e911fa0` statically — all 107 tracked files (docs-only delta
  from the code snapshot `b735b90`) — plus CI run `42934586787` cross-checked read-only
  via `gh run view --log` (it checks out `b735b90` exactly). All checks pass and
  local/CI agree (backend 113 passed — local's 1 warning vs CI's 2 is the disclosed
  Linux-only passlib `crypt` notice; Ruff clean; ESLint clean; Vitest 12 files/32
  tests; audit 0; build green with identical hashes), so there are **no blocking
  issues**. All 14 prior findings verified genuinely resolved in code, none
  reintroduced; R-009's execution half is accepted as a justified environmental
  deferral (Docker not installed, disclosed prominently, exactly as the protocol
  requires) and remains tracked. Verdict is **REJECT** with **one new finding,
  R-015**: the backend Docker image omits `alembic.ini` and `alembic/`, so it cannot
  boot outside Compose — the `./backend:/app` bind mount is the only thing making the
  documented stack work, and the missing execution R-009 asked for is exactly why it
  went unnoticed. The fix is two static `COPY` lines, no Docker needed. Full detail:
  [`docs/rounds/round-02-review.md`](docs/rounds/round-02-review.md).
