# Round 2 — Developer handoff

## 1. Commit SHA and full file manifest

**Snapshot SHA (code): `b735b9018ed9218e646ac4d1ff295535523bbe8b`** (`master`, pushed to
`https://github.com/M-A-E-A/fairschedule-ai`). CI run **`42934586787`** checked out this
exact SHA (fetch ref and `git log -1` in the pasted log confirm it) and both jobs are
green. The only later commit is this handoff plus the `ISSUES.md` round entry
themselves, which add no code — same convention as round 1.

Round-2 commits, oldest first:

- `2862470` — R-001: revalidate proposal rows against current data before approval
- `867a848` — R-002: refuse SSO linking/provisioning on unverified provider email
- `3db21fc` — R-003: revalidate room capacity/type/campus edits against existing bookings
- `95deee0` — R-006/R-007/R-008: tenant-scope all dashboard/AI lookups, scope by role
  not link, schema-validated AI prompt
- `2394eb6` — R-014: equalize login timing via dummy bcrypt verify, throttle repeated
  login failures per IP/account
- `64a60ed` — R-004/R-005/R-009/R-010/R-011: Compose CORS origin fix, JWT secret via
  env, production frontend image, demo docs
- `f413d85` — R-012/R-013: drop unused drei, upgrade toolchain to a 0-vulnerability
  tree, add CI audit gate
- `b735b90` — fix CI build failure after the toolchain upgrade
  (`moduleResolution: bundler`)

`git ls-files` manifest (106 tracked files at `b735b90`; the handoff commit adds only
`docs/rounds/round-02-handoff.md` as the 107th):

```
.env.example
.github/workflows/ci.yml
.gitignore
ISSUES.md
README.md
backend/.dockerignore
backend/Dockerfile
backend/alembic.ini
backend/alembic/README
backend/alembic/env.py
backend/alembic/script.py.mako
backend/alembic/versions/72bbb9943009_initial_schema.py
backend/app/__init__.py
backend/app/api/__init__.py
backend/app/api/admin.py
backend/app/api/ai.py
backend/app/api/auth.py
backend/app/api/bookings.py
backend/app/api/dashboard.py
backend/app/api/deps.py
backend/app/api/rooms.py
backend/app/api/scheduling.py
backend/app/core/__init__.py
backend/app/core/config.py
backend/app/core/db.py
backend/app/core/migrations.py
backend/app/core/roles.py
backend/app/core/security.py
backend/app/main.py
backend/app/models/__init__.py
backend/app/models/tenant.py
backend/app/schemas/ai.py
backend/app/schemas/auth.py
backend/app/schemas/scheduling.py
backend/app/seed.py
backend/app/services/rate_limit.py
backend/app/services/scheduler.py
backend/app/services/sso.py
backend/pytest.ini
backend/requirements.txt
backend/ruff.toml
backend/tests/conftest.py
backend/tests/test_admin_users.py
backend/tests/test_api.py
backend/tests/test_auth.py
backend/tests/test_dashboard_ai.py
backend/tests/test_login_throttle.py
backend/tests/test_proposal_revalidation.py
backend/tests/test_rbac.py
backend/tests/test_rooms_bookings.py
backend/tests/test_scheduler_unit.py
backend/tests/test_scheduling_api.py
backend/tests/test_sso.py
backend/tests/test_tenant_isolation.py
docker-compose.yml
docs/AGENT_PROTOCOL.md
docs/PROJECT.md
docs/prompts/DEVELOPER.md
docs/prompts/REVIEWER.md
docs/rounds/round-01-handoff.md
docs/rounds/round-01-review.md
frontend/.dockerignore
frontend/Dockerfile
frontend/eslint.config.js
frontend/index.html
frontend/nginx.conf
frontend/package-lock.json
frontend/package.json
frontend/src/App.test.tsx
frontend/src/App.tsx
frontend/src/api.ts
frontend/src/auth/AuthProvider.tsx
frontend/src/auth/context.ts
frontend/src/components/AppShell.test.tsx
frontend/src/components/AppShell.tsx
frontend/src/components/LottieLoader.test.tsx
frontend/src/components/LottieLoader.tsx
frontend/src/components/RequireRole.test.tsx
frontend/src/components/RequireRole.tsx
frontend/src/main.tsx
frontend/src/pages/AdminUsersPage.test.tsx
frontend/src/pages/AdminUsersPage.tsx
frontend/src/pages/AiPage.test.tsx
frontend/src/pages/AiPage.tsx
frontend/src/pages/CampusPage.test.tsx
frontend/src/pages/CampusPage.tsx
frontend/src/pages/DashboardPage.test.tsx
frontend/src/pages/DashboardPage.tsx
frontend/src/pages/LandingPage.tsx
frontend/src/pages/LoginPage.test.tsx
frontend/src/pages/LoginPage.tsx
frontend/src/pages/MySchedulePage.test.tsx
frontend/src/pages/MySchedulePage.tsx
frontend/src/pages/RoomsPage.test.tsx
frontend/src/pages/RoomsPage.tsx
frontend/src/pages/TimetablePage.test.tsx
frontend/src/pages/TimetablePage.tsx
frontend/src/setupTests.ts
frontend/src/styles.css
frontend/src/testUtils.tsx
frontend/src/types.ts
frontend/src/useApi.ts
frontend/src/vite-env.d.ts
frontend/tsconfig.json
frontend/tsconfig.node.json
frontend/vite.config.ts
```

## 2. What was built this round

All 14 findings from
[`docs/rounds/round-01-review.md`](round-01-review.md) were implemented. Backend tests
went 96 → **113**, frontend stayed green through a major toolchain upgrade.

### R-001 — Proposal approval revalidates against current data (`2862470`)

`approve_proposal` no longer trusts the stored solver rows. It calls
`_revalidate_proposal` (`backend/app/api/scheduling.py`), which:

- loads the tenant's **current** bookings, rooms, courses, and groups (all
  institution-scoped);
- rejects `409` on stale references: a proposed session that was deleted, moved to
  another campus, or whose room was deleted or moved off the proposal's campus;
- reconstructs the **post-application state** — every current booking with each
  proposal row applied on top, untouched bookings keeping their stored times — and
  runs `count_hard_violations` over the whole reconstructed state (room/lecturer/group
  overlap, capacity, room type, availability window; the generation `day_start` /
  `day_end` window travels with the proposal payload, so moved sessions are rechecked
  against the same window);
- rejects `409` if any violation is found, and writes a `proposal_rejected` audit
  event for the refusal itself; only a clean revalidation applies rows and writes the
  `proposal_approved` event (which states that constraints were revalidated).

Generation now stores its parameters in the proposal payload, because approval needs
them. 5 regression tests in `backend/tests/test_proposal_revalidation.py`:
booking created after generation, session deleted, session moved to another campus,
room moved off the proposal campus, room shrunk below a cohort.

### R-002 — SSO never links on an unverified email (`867a848`)

`exchange_code_for_identity` (`backend/app/services/sso.py`) now returns the
`email_verified` claim from the userinfo response. `_resolve_sso_user`
(`backend/app/api/auth.py`) applies it:

- an identity already linked by (`external_subject`, `external_provider`) signs in as
  before — that binding was established under the verified-email rule;
- linking to an **existing** account (any role, including administrators) requires
  `email_verified` true, else `403 "email not verified by provider"` — the exact fix
  the review specified;
- **provisioning** a new account applies the same check (the review allowed either;
  the stricter rule also stops an unverified address from shadowing someone else's
  email). A missing `email_verified` claim is treated as unverified.

4 new tests in `backend/tests/test_sso.py` (cannot link, cannot provision, missing
claim treated as unverified, service reads the claim), and the existing SSO test
identities now carry `email_verified`.

### R-003 — Room edits never invalidate existing bookings (`3db21fc`)

`update_room` (`backend/app/api/rooms.py`) calls `_validate_room_change` whenever
`capacity`, `room_type`, or `campus_id` changes. It loads every booking referencing
the room (plus the tenant's courses and groups) and rejects `409` with the offending
booking named, when:

- a capacity shrink would seat fewer than a referencing booking's cohort size;
- a room-type change would break a referencing course's `required_room_type`
  (courses requiring `any`/empty are unaffected);
- a campus move would strand bookings on their current campus.

The documented policy is **reject** (the review's first option): the operator must
move or reassign those sessions first. Regression test:
`test_room_edit_never_invalidates_existing_bookings` covers refusal on each dimension
plus the happy paths.

### R-006 / R-007 / R-008 — scoping and API-shape fixes (`95deee0`)

- **R-006:** every lookup dict in `dashboard.py`, `scheduling.py`, and `ai.py` is now
  built from institution-filtered queries (`Model.institution_id == …`); no
  unscoped `select(Course/Lecturer/StudentGroup/Room)` remains in those modules.
- **R-007:** `/me/schedule` and the AI context branch on **role first** — student →
  cohort, faculty → lecturer-scoped with an explicit `note` when unlinked,
  campus-operator/administrator → institution scope regardless of any lecturer link
  on the account. The duplicated `lecturer_id` guard was removed from
  `_faculty_context` (its `None` branch is now reachable from the AI path).
- **R-008:** `POST /ai/chat` takes `AiChatRequest` (`backend/app/schemas/ai.py`):
  `prompt: str` with `min_length=1`, `max_length=2000`, and a validator rejecting
  blank/whitespace-only prompts. Validation is schema-driven (422) like every other
  endpoint.

R-007's scoping change carries its own regression test
(`test_me_schedule_scopes_on_role_not_lecturer_link`: an administrator with a lecturer
link still gets institution scope, an unlinked faculty user gets the explicit note),
and the schema/422 behaviour of `AiChatRequest` is covered in
`backend/tests/test_dashboard_ai.py`. Backend tests went 96 → 113 across the round
(5 proposal revalidation + 4 SSO verified-email + 1 room-edit revalidation + 1 role
scoping + 6 login throttling).

### R-014 — login timing equalization and throttling (`2394eb6`)

- Unknown usernames/emails now verify against a fixed `DUMMY_PASSWORD_HASH`, so every
  401 pays exactly one bcrypt verification — the timing oracle is gone
  (`backend/app/core/security.py`, `login` in `auth.py`).
- `backend/app/services/rate_limit.py` adds an in-memory sliding-window limiter keyed
  by (client IP, attempted identifier): 5 failures inside 15 minutes → `429` with
  `Retry-After` for that pair, equally for existing and nonexistent accounts (the key
  is the attempted identifier, so lockout itself leaks nothing). A successful login
  resets the counter. The per-process scope is a documented decision (single-worker
  SQLite design; multi-worker deployments would move the store to shared
  infrastructure).
- 6 tests in `backend/tests/test_login_throttle.py`, including a structural
  spy on `verify_password` (asserting the dummy hash is verified exactly once for
  unknown accounts) rather than flaky wall-clock timing assertions.

### R-004 / R-005 / R-009 / R-010 / R-011 — Compose and documentation fixes (`64a60ed`)

- **R-004:** `docker-compose.yml` sets `BACKEND_CORS_ORIGINS: http://localhost:5173`
  (the browser origin), with a comment explaining why the container hostname never
  appears in a browser `Origin` header.
- **R-005:** the committed `JWT_SECRET: change-me` line is removed; with
  `APP_ENV=development` the backend's existing ephemeral per-process secret applies,
  so no secret value ships in the repo.
- **R-009:** `frontend/Dockerfile` is now a production image: stage 1 `node:20-alpine`
  runs `npm ci` + `npm run build` (with `VITE_API_BASE_URL` passed as a build
  argument, since Vite bakes `VITE_*` at build time); stage 2 serves `dist/` with
  `nginx:1.27-alpine` on port 5173, with `frontend/nginx.conf` providing SPA fallback
  routing so deep links/refreshes work. `docker-compose.yml` passes the build arg.
- **R-010:** `USE_SQLITE_FOR_TESTS` deleted from `.env.example` (nothing read it).
- **R-011:** README corrected to the real default (`sqlite:///./demo.db`), and the
  seeded second-tenant account `harbor-admin` / `demo-admin-harbor` (Harbor College)
  documented in both the README and the login-page demo hint.
- **Docker is still not installed on this machine**, so the Compose stack remains
  **statically verified only** — see section 9.

### R-012 / R-013 — dependency overhaul (`f413d85`, completed and fixed by `b735b90`)

The tree inherited an uncommitted, half-finished dependency migration. I found it in
this state: `package.json` already declared the upgrades (drei removed, router 7,
vite 8, vitest 5, plugin-react 5, `@types/three`, `minimatch` override), `node_modules`
was installed against it, but **the lockfile was missing the `@types/three` tree**
(`npm ci` failed with `Missing: @types/three@0.170.0 from lock file`). I completed it:

- regenerated `package-lock.json` (`npm install`), then verified reproducibility with
  `npm ci`;
- **verified the `minimatch` override is load-bearing**: removing it re-introduces
  10 moderate advisories (GHSA-g3hv-75wg-m249, globparts DoS) through
  `eslint@10`/`typescript-eslint@8.72`; npm's own suggested fix (`npm audit fix
  --force`) is a **downgrade to eslint 9**, a breaking change. The override pins
  `minimatch@^11.0.5`, the patched release — kept deliberately, with this reasoning
  recorded here and in the commit message;
- `npm audit` now reports **0 vulnerabilities** (CI reported 18 in round 1: 2
  critical, 1 high, 15 moderate);
- **R-012:** `@react-three/drei` is gone from `package.json` and the lockfile; no
  source file imported it (verified by search), and the `three-mesh-bvh` deprecation
  warning that appeared in round-1's CI log is gone from this round's CI log;
- **R-013:** the review noted no audit gate existed to catch regressions, so CI now
  runs `npm audit --audit-level=high` right after `npm ci` (`f413d85`). With 0
  vulnerabilities it is green today and any future high/critical advisory fails the
  build instead of passing silently;
- source compatibility with the upgrades was verified: all React Router usage is
  v6→v7 compatible API (`BrowserRouter`/`Routes`/`NavLink`/`Outlet`/`useNavigate`/
  `useLocation`/`useOutletContext`/`Navigate`/`MemoryRouter`), and the v6 future-flag
  warnings that filled round-1's local test output are gone;
- the first push of this round **failed CI** (`f413d85`, run `42934118803`): the Build
  step died with `TS2307: Cannot find module '@vitejs/plugin-react'` because
  plugin-react v5 resolves types through its `exports` map, which the legacy
  `moduleResolution: "Node"` cannot read. Local runs had passed only because a stale
  `tsconfig.node.tsbuildinfo` incremental cache let `tsc -b` skip rechecking
  `vite.config.ts` — a genuine local/CI mismatch of exactly the kind the handoff
  rules exist to catch. `b735b90` sets `moduleResolution: "bundler"` (with
  `module: ESNext`) in both tsconfigs — the setting current Vite scaffolds generate —
  and the fix was re-verified **from a clean state**: all `*.tsbuildinfo` caches and the
  generated `vite.config.js` deleted, then lint/test/build/audit re-run locally, then
  CI re-run green on `b735b90` with the same asset hashes as local.

### Regression-test quality verification

Beyond passing, each of the three substantive fixes was proven to have a test that
**fails without the fix** — each fix was temporarily neutralized, the test suite run,
and the file restored (`git checkout --`):

- R-001: with `_revalidate_proposal` disabled, all 5 tests in
  `test_proposal_revalidation.py` fail (5 failed, 1 warning).
- R-002: with the verified-email gate forced to `True`, the 3 endpoint-level tests
  fail (`test_unverified_email_cannot_link_existing_account`,
  `test_unverified_email_cannot_provision`,
  `test_missing_email_verified_claim_is_treated_as_unverified`; 3 failed, 12 passed).
- R-003: with `_validate_room_change` skipped,
  `test_room_edit_never_invalidates_existing_bookings` fails (1 failed, 9 passed).

The tree was restored to the committed state afterwards (`git status` clean apart from
the frontend dependency files being migrated at that time).

## 3. Status of every prior open issue from `ISSUES.md`

| ID | Status | How / justification |
|----|--------|---------------------|
| R-001 | resolved | `approve_proposal` revalidates: stale-reference checks + full post-application reconstruction + `count_hard_violations` re-run; `409` and audited refusal on violation; 5 regression tests (`2862470`). |
| R-002 | resolved | `email_verified` claim surfaced by the service; linking to an existing account and provisioning both require it (`403 "email not verified by provider"`); subject-matched existing links unaffected; 4 tests (`867a848`). |
| R-003 | resolved | capacity/room-type/campus edits revalidated against every referencing booking, rejected with `409` naming the booking; documented policy; regression test (`3db21fc`). |
| R-004 | resolved | Compose `BACKEND_CORS_ORIGINS` is now the browser origin `http://localhost:5173` (`64a60ed`). Stack still not executed — Docker absent (section 9). |
| R-005 | resolved | committed `JWT_SECRET` removed from `docker-compose.yml`; ephemeral per-process dev secret applies (`64a60ed`). |
| R-006 | resolved | all dashboard/scheduling/ai lookup queries institution-scoped (`95deee0`). |
| R-007 | resolved | `/me/schedule` and AI context branch on role first; unlinked faculty get an explicit note; dead branch removed from `_faculty_context` (`95deee0`). |
| R-008 | resolved | `AiChatRequest` Pydantic schema with min/max length and blank rejection; schema-driven 422s (`95deee0`). |
| R-009 | resolved (code) | frontend image is a production multi-stage build served by nginx on 5173 with SPA fallback; `VITE_API_BASE_URL` passed as build arg (`64a60ed`). Execution of the stack remains impossible on this machine — Docker is not installed; see section 9. |
| R-010 | resolved | `USE_SQLITE_FOR_TESTS` deleted from `.env.example` (`64a60ed`). |
| R-011 | resolved | README default-DB line corrected to `sqlite:///./demo.db`; `harbor-admin` documented in README and the login-page demo hint (`64a60ed`). |
| R-012 | resolved | `@react-three/drei` removed from `package.json` + lockfile; never imported by source; three-mesh-bvh warning gone from CI (`f413d85`). |
| R-013 | resolved | toolchain upgraded (router 7, vite 8, vitest 5, plugin-react 5, `@types/three`), lockfile regenerated, `minimatch` pinned to patched `^11.0.5` via override (npm's suggested fix is a breaking eslint downgrade); `npm audit` = **0 vulnerabilities** (was 18); `npm audit --audit-level=high` added as a CI gate (`f413d85`, `b735b90`). |
| R-014 | resolved | dummy-hash bcrypt verification equalizes every 401's cost; sliding-window per-(IP, identifier) lockout (5 failures / 15 min → 429 + `Retry-After`), identical for unknown accounts, success resets; 6 tests (`2394eb6`). |

## 4. Raw local test output (verbatim)

Backend — `cd backend && python -m pytest -q`:

```
........................................................................ [ 63%]
.........................................                                [100%]
============================== warnings summary ===============================
..\..\..\AppData\Local\Programs\Python\Python312\Lib\site-packages\starlette\testclient.py:40
  C:\Users\Hp\AppData\Local\Programs\Python\Python312\Lib\site-packages\starlette\testclient.py:40: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = typing.Callable[[], anyio.abc.BlockingPortal]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
113 passed, 1 warning in 55.03s
```

Frontend — `cd frontend && npm run test -- --run` (ANSI colour codes stripped,
content otherwise exact):

```
> fairschedule-ai-frontend@0.1.0 test
> vitest run --run


 RUN  v5.1.0 C:/Users/Hp/Desktop/the next big project/frontend


 Test Files  12 passed (12)
      Tests  32 passed (32)
   Start at  23:49:58
   Duration  16.59s (environment 49%, import 21%, tests 18%, setup 10%, transform 2%, worker 1%)

Environment  jsdom was created 12 times · 28.14s total, 49% of tracked time
             create it once per worker with pool: 'vmThreads' (keeps per-file isolation) or isolate: false (shares it across files)
             learn more: https://vitest.dev/guide/improving-performance#test-environment
```

## 5. Raw local lint output (verbatim)

Backend — `cd backend && python -m ruff check .`:

```
All checks passed!
```

Frontend — `cd frontend && npm run lint`:

```
> fairschedule-ai-frontend@0.1.0 lint
> eslint .
```

No output after the script banner; exit code 0.

Frontend — `cd frontend && npm audit --audit-level=high` (the new CI gate, run
locally too):

```
found 0 vulnerabilities
```

## 6. Raw local build output (verbatim)

Frontend — `cd frontend && npm run build` (ANSI colour codes stripped, content
otherwise exact; the `NativeCommandError` block is PowerShell echoing vite's stderr
warnings — a known local-shell quirk — and is not npm output; the build succeeded,
`✓ built in 918ms`, exit code 0):

```
> fairschedule-ai-frontend@0.1.0 build
> tsc -b && vite build

vite v8.3.7 building client environment for production...
transforming...
✓ 59 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                     0.41 kB │ gzip:   0.27 kB
dist/assets/index-SvLVliAF.css      7.24 kB │ gzip:   2.21 kB
dist/assets/index-BrSS0O_p.js   1,547.58 kB │ gzip: 420.28 kB

(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rolldownOptions.output.codeSplitting to improve chunking:
https://rolldown.rs/reference/OutputOptions.codeSplitting
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
[EVAL] Use of direct `eval` function is strongly discouraged as it poses security risks and may cause issues with
minification.
       node_modules/lottie-web/build/player/lottie.js:14422:33
  14422 │ var expression = eval('[function _expression_' + val + '(){' + val + ';}compiled_return = $compiled_return}]')[0]; // eslint-disable-line
       │                                                                                                        ──┬─
       │                                                                                                          ╰─── Use of direct `eval` here.

✓ built in 918ms
```

The two warnings are pre-existing and non-fatal: the chunk-size notice (the bundle is
single-file by design; drei's removal trimmed `node_modules`, not the bundle, since it
was never imported) and lottie-web's internal direct-eval (a third-party library,
unchanged since round 1). `tsc -b` passed **from a clean state** — all `*.tsbuildinfo`
caches and the generated `vite.config.js` were deleted before this run, so this is
the same check CI performs (see section 2, R-012/R-013).

## 7. Full CI log for the run on the push, verbatim

Run: **`42934586787`** — https://github.com/M-A-E-A/fairschedule-ai/actions/runs/42934586787
Conclusion: **success** (both jobs green) on commit
`b735b9018ed9218e646ac4d1ff295535523bbe8b`.

Note: the *first* push of this round (`f413d85`) failed CI in the frontend Build step
(run `42934118803`, `TS2307 Cannot find module '@vitejs/plugin-react'` — root cause
and fix in section 2). `b735b90` fixed it; the log below is the full log of the green
run on that final code commit. `gh run view 42934586787 --log` output, verbatim (the
CLI's ANSI colour sequences appear as `^[[…` exactly as emitted):

```
Backend (lint + test)	Set up job	´╗┐2026-11-11T00:51:20.6969593Z Current runner version: '2.338.2'
Backend (lint + test)	Set up job	2026-11-11T00:51:20.6991411Z ##[group]Runner Image Provisioner
Backend (lint + test)	Set up job	2026-11-11T00:51:20.6992165Z Hosted Compute Agent
Backend (lint + test)	Set up job	2026-11-11T00:51:20.6992646Z Version: 20261028.624
Backend (lint + test)	Set up job	2026-11-11T00:51:20.6993236Z Commit: 54898b74c23fde5556c9b3c3a2290865feef0dfe
Backend (lint + test)	Set up job	2026-11-11T00:51:20.6993837Z Build Date: 2026-10-28T21:51:42Z
Backend (lint + test)	Set up job	2026-11-11T00:51:20.6994413Z Worker ID: {21bba714-6d3c-453c-967c-086bb80e694d}
Backend (lint + test)	Set up job	2026-11-11T00:51:20.6995035Z Region: westus2
Backend (lint + test)	Set up job	2026-11-11T00:51:20.6995502Z Cloud: Azure
Backend (lint + test)	Set up job	2026-11-11T00:51:20.6996243Z ##[endgroup]
Backend (lint + test)	Set up job	2026-11-11T00:51:20.6997420Z ##[group]Operating System
Backend (lint + test)	Set up job	2026-11-11T00:51:20.6998001Z Ubuntu
Backend (lint + test)	Set up job	2026-11-11T00:51:20.6998477Z 26.04.1
Backend (lint + test)	Set up job	2026-11-11T00:51:20.6998902Z LTS
Backend (lint + test)	Set up job	2026-11-11T00:51:20.6999370Z ##[endgroup]
Backend (lint + test)	Set up job	2026-11-11T00:51:20.6999850Z ##[group]Runner Image
Backend (lint + test)	Set up job	2026-11-11T00:51:20.7000333Z Image: ubuntu-26.04
Backend (lint + test)	Set up job	2026-11-11T00:51:20.7000878Z Version: 20261101.186.1
Backend (lint + test)	Set up job	2026-11-11T00:51:20.7001740Z Included Software: https://github.com/actions/runner-images/blob/ubuntu26/20261101.186/images/ubuntu/Ubuntu2604-Readme.md
Backend (lint + test)	Set up job	2026-11-11T00:51:20.7003171Z Image Release: https://github.com/actions/runner-images/releases/tag/ubuntu26%2F20261101.186
Backend (lint + test)	Set up job	2026-11-11T00:51:20.7003932Z ##[endgroup]
Backend (lint + test)	Set up job	2026-11-11T00:51:20.7004984Z ##[group]GITHUB_TOKEN Permissions
Backend (lint + test)	Set up job	2026-11-11T00:51:20.7006800Z Contents: read
Backend (lint + test)	Set up job	2026-11-11T00:51:20.7007395Z Metadata: read
Backend (lint + test)	Set up job	2026-11-11T00:51:20.7007903Z Packages: read
Backend (lint + test)	Set up job	2026-11-11T00:51:20.7008430Z ##[endgroup]
Backend (lint + test)	Set up job	2026-11-11T00:51:20.7010083Z Secret source: Actions
Backend (lint + test)	Set up job	2026-11-11T00:51:20.7011175Z Cache mode: write
Backend (lint + test)	Set up job	2026-11-11T00:51:20.7011757Z Prepare workflow directory
Backend (lint + test)	Set up job	2026-11-11T00:51:20.7407879Z Prepare all required actions
Backend (lint + test)	Set up job	2026-11-11T00:51:20.7524842Z Getting action download info
Backend (lint + test)	Set up job	2026-11-11T00:51:21.0639709Z Download action repository 'actions/checkout@v4' (SHA:11d5960a326750d5838078e36cf38b85af677262)
Backend (lint + test)	Set up job	2026-11-11T00:51:21.1950863Z Download action repository 'actions/setup-python@v5' (SHA:a26af69be951a213d495a4c3e4e4022e16d87065)
Backend (lint + test)	Set up job	2026-11-11T00:51:21.4069813Z Complete job name: Backend (lint + test)
Backend (lint + test)	Run actions/checkout@v4	´╗┐2026-11-11T00:51:21.4847233Z ##[group]Run actions/checkout@v4
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4847945Z with:
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4848321Z   repository: M-A-E-A/fairschedule-ai
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4851461Z   token: ***
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4851819Z   ssh-strict: true
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4852188Z   ssh-user: git
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4852547Z   persist-credentials: true
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4852944Z   clean: true
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4853305Z   sparse-checkout-cone-mode: true
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4853725Z   fetch-depth: 1
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4854086Z   fetch-tags: false
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4854448Z   show-progress: true
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4854809Z   lfs: false
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4855141Z   submodules: false
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4855505Z   set-safe-directory: true
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4855917Z   allow-unsafe-pr-checkout: false
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.4856689Z ##[endgroup]
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.7318496Z Syncing repository: M-A-E-A/fairschedule-ai
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.7422041Z ##[group]Getting Git version info
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.7427211Z Working directory is '/home/runner/work/fairschedule-ai/fairschedule-ai'
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.7429072Z [command]/usr/bin/git version
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.7429879Z git version 2.56.0
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.7432218Z ##[endgroup]
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.7447186Z Temporarily overriding HOME='/home/runner/work/_temp/aafe0248-755a-48e3-a9a8-0f0f1486c952' before making global git config changes
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.7458964Z Adding repository directory to the temporary git global config as a safe directory
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.7460567Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/fairschedule-ai/fairschedule-ai
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8401640Z Deleting the contents of '/home/runner/work/fairschedule-ai/fairschedule-ai'
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8403496Z ##[group]Initializing the repository
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8404621Z [command]/usr/bin/git init /home/runner/work/fairschedule-ai/fairschedule-ai
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8406124Z hint: Using 'master' as the name for the initial branch. This default branch name
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8408828Z hint: will change to "main" in Git 3.0. To configure the initial branch name
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8410419Z hint: to use in all of your new repositories, which will suppress this warning,
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8411967Z hint: call:
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8412739Z hint:
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8413925Z hint: 	git config --global init.defaultBranch <name>
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8414987Z hint:
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8416370Z hint: Names commonly chosen instead of 'master' are 'main', 'trunk' and
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8417950Z hint: 'development'. The just-created branch can be renamed via this command:
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8419508Z hint:
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8421933Z hint: 	git branch -m <name>
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8422565Z hint:
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8423361Z hint: Disable this message with "git config set advice.defaultBranchName false"
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8424706Z Initialized empty Git repository in /home/runner/work/fairschedule-ai/fairschedule-ai/.git/
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8427185Z [command]/usr/bin/git remote add origin https://github.com/M-A-E-A/fairschedule-ai
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8429223Z ##[endgroup]
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8429998Z ##[group]Disabling automatic garbage collection
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8430860Z [command]/usr/bin/git config --local gc.auto 0
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8432554Z ##[endgroup]
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8433426Z ##[group]Setting up auth
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8434353Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8446774Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8680522Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8712472Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.8996207Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.9015953Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.9270678Z [command]/usr/bin/git config --local http.https://github.com/.extraheader AUTHORIZATION: basic ***
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.9310128Z ##[endgroup]
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.9311692Z ##[group]Fetching the repository
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:21.9319965Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +b735b9018ed9218e646ac4d1ff295535523bbe8b:refs/remotes/origin/master
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:22.2837225Z From https://github.com/M-A-E-A/fairschedule-ai
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:22.2838743Z  * [new ref]         b735b9018ed9218e646ac4d1ff295535523bbe8b -> origin/master
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:22.2843564Z ##[endgroup]
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:22.2844764Z ##[group]Determining the checkout info
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:22.2846541Z ##[endgroup]
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:22.2852537Z [command]/usr/bin/git sparse-checkout disable
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:22.2902193Z [command]/usr/bin/git config --local --unset-all extensions.worktreeConfig
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:22.2930838Z ##[group]Checking out the ref
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:22.2934263Z [command]/usr/bin/git checkout --progress --force -B master refs/remotes/origin/master
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:22.3043666Z Reset branch 'master'
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:22.3049110Z branch 'master' set up to track 'origin/master'.
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:22.3065004Z ##[endgroup]
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:22.3096138Z [command]/usr/bin/git log -1 --format=%H
Backend (lint + test)	Run actions/checkout@v4	2026-11-11T00:51:22.3119736Z b735b9018ed9218e646ac4d1ff295535523bbe8b
Backend (lint + test)	Run actions/setup-python@v5	´╗┐2026-11-11T00:51:22.3376434Z ##[group]Run actions/setup-python@v5
Backend (lint + test)	Run actions/setup-python@v5	2026-11-11T00:51:22.3376917Z with:
Backend (lint + test)	Run actions/setup-python@v5	2026-11-11T00:51:22.3377250Z   python-version: 3.12
Backend (lint + test)	Run actions/setup-python@v5	2026-11-11T00:51:22.3377629Z   check-latest: false
Backend (lint + test)	Run actions/setup-python@v5	2026-11-11T00:51:22.3380577Z   token: ***
Backend (lint + test)	Run actions/setup-python@v5	2026-11-11T00:51:22.3380932Z   update-environment: true
Backend (lint + test)	Run actions/setup-python@v5	2026-11-11T00:51:22.3381492Z   allow-prereleases: false
Backend (lint + test)	Run actions/setup-python@v5	2026-11-11T00:51:22.3381873Z   freethreaded: false
Backend (lint + test)	Run actions/setup-python@v5	2026-11-11T00:51:22.3382229Z ##[endgroup]
Backend (lint + test)	Run actions/setup-python@v5	2026-11-11T00:51:22.4508254Z ##[group]Installed versions
Backend (lint + test)	Run actions/setup-python@v5	2026-11-11T00:51:22.4656697Z (node:2079) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
Backend (lint + test)	Run actions/setup-python@v5	2026-11-11T00:51:22.4658423Z Successfully set up CPython (3.12.16)
Backend (lint + test)	Run actions/setup-python@v5	2026-11-11T00:51:22.4659596Z (Use `node --trace-deprecation ...` to show where the warning was created)
Backend (lint + test)	Run actions/setup-python@v5	2026-11-11T00:51:22.4685729Z ##[endgroup]
Backend (lint + test)	Run python -m pip install --upgrade pip	´╗┐2026-11-11T00:51:22.4999141Z ##[group]Run python -m pip install --upgrade pip
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:22.5000121Z ^[[36;1mpython -m pip install --upgrade pip^[[0m
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:22.5087609Z shell: /usr/bin/bash -e {0}
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:22.5088100Z env:
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:22.5088530Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:22.5089224Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.16/x64/lib/pkgconfig
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:22.5089962Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:22.5090550Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:22.5091155Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:22.5091755Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.16/x64/lib
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:22.5092269Z ##[endgroup]
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:24.2419579Z Requirement already satisfied: pip in /opt/hostedtoolcache/Python/3.12.16/x64/lib/python3.12/site-packages (26.2.2)
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:24.3300890Z Collecting pip
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:24.3632778Z   Downloading pip-26.3-py3-none-any.whl.metadata (4.6 kB)
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:24.3741065Z Downloading pip-26.3-py3-none-any.whl (2.0 MB)
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:24.4233826Z    ÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöü 2.0/2.0 MB 53.0 MB/s  0:00:00
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:24.5518070Z Installing collected packages: pip
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:24.5518803Z   Attempting uninstall: pip
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:24.5519231Z     Found existing installation: pip 26.2.2
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:24.5971369Z     Uninstalling pip-26.2.2:
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:24.6020564Z       Successfully uninstalled pip-26.2.2
Backend (lint + test)	Run python -m pip install --upgrade pip	2026-11-11T00:51:25.5137142Z Successfully installed pip-26.3
Backend (lint + test)	Run pip install -r backend/requirements.txt	´╗┐2026-11-11T00:51:25.5542089Z ##[group]Run pip install -r backend/requirements.txt
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:25.5542644Z ^[[36;1mpip install -r backend/requirements.txt^[[0m
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:25.5590608Z shell: /usr/bin/bash -e {0}
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:25.5590891Z env:
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:25.5591208Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:25.5591600Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.16/x64/lib/pkgconfig
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:25.5591972Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:25.5592312Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:25.5592653Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:25.5592989Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.16/x64/lib
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:25.5593294Z ##[endgroup]
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:25.9317142Z Collecting fastapi==0.115.0 (from -r backend/requirements.txt (line 1))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:25.9660196Z   Downloading fastapi-0.115.0-py3-none-any.whl.metadata (27 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:25.9905928Z Collecting uvicorn==0.30.6 (from uvicorn[standard]==0.30.6->-r backend/requirements.txt (line 2))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:25.9984962Z   Downloading uvicorn-0.30.6-py3-none-any.whl.metadata (6.6 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.0271511Z Collecting sqlmodel==0.0.15 (from -r backend/requirements.txt (line 3))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.0375224Z   Downloading sqlmodel-0.0.15-py3-none-any.whl.metadata (9.8 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.3483610Z Collecting sqlalchemy==2.0.35 (from -r backend/requirements.txt (line 4))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.3877413Z   Downloading SQLAlchemy-2.0.35-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (9.6 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.4136226Z Collecting pydantic-settings==2.5.2 (from -r backend/requirements.txt (line 5))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.4213749Z   Downloading pydantic_settings-2.5.2-py3-none-any.whl.metadata (3.5 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.4358860Z Collecting python-jose==3.5.0 (from python-jose[cryptography]==3.5.0->-r backend/requirements.txt (line 6))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.4449004Z   Downloading python_jose-3.5.0-py2.py3-none-any.whl.metadata (5.5 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.4603512Z Collecting passlib==1.7.4 (from passlib[bcrypt]==1.7.4->-r backend/requirements.txt (line 7))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.4682419Z   Downloading passlib-1.7.4-py2.py3-none-any.whl.metadata (1.7 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.4979878Z Collecting bcrypt==4.0.1 (from -r backend/requirements.txt (line 11))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.5050104Z   Downloading bcrypt-4.0.1-cp36-abi3-manylinux_2_28_x86_64.whl.metadata (9.0 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.5193363Z Collecting python-multipart==0.0.9 (from -r backend/requirements.txt (line 12))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.5297323Z   Downloading python_multipart-0.0.9-py3-none-any.whl.metadata (2.5 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.5584952Z Collecting ortools==9.10.4067 (from -r backend/requirements.txt (line 13))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.5685312Z   Downloading ortools-9.10.4067-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (2.9 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.5841802Z Collecting psycopg==3.3.8 (from psycopg[binary]==3.3.8->-r backend/requirements.txt (line 14))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.5909041Z   Downloading psycopg-3.3.8-py3-none-any.whl.metadata (4.4 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.6061868Z Collecting email-validator==2.2.0 (from -r backend/requirements.txt (line 15))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.6134414Z   Downloading email_validator-2.2.0-py3-none-any.whl.metadata (25 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.6500256Z Collecting alembic==1.20.1 (from -r backend/requirements.txt (line 16))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.6566691Z   Downloading alembic-1.20.1-py3-none-any.whl.metadata (7.3 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.9434242Z Collecting ruff==0.17.4 (from -r backend/requirements.txt (line 17))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.9527594Z   Downloading ruff-0.17.4-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (20 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.9765468Z Collecting pytest==8.3.3 (from -r backend/requirements.txt (line 18))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:26.9831410Z   Downloading pytest-8.3.3-py3-none-any.whl.metadata (7.5 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.0000896Z Collecting pytest-asyncio==0.24.0 (from -r backend/requirements.txt (line 19))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.0096321Z   Downloading pytest_asyncio-0.24.0-py3-none-any.whl.metadata (3.9 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.0300605Z Collecting httpx==0.27.2 (from -r backend/requirements.txt (line 20))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.0379672Z   Downloading httpx-0.27.2-py3-none-any.whl.metadata (7.1 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.0634690Z Collecting starlette<0.39.0,>=0.37.2 (from fastapi==0.115.0->-r backend/requirements.txt (line 1))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.0732778Z   Downloading starlette-0.38.6-py3-none-any.whl.metadata (6.0 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.1550928Z Collecting pydantic!=1.8,!=1.8.1,!=2.0.0,!=2.0.1,!=2.1.0,<3.0.0,>=1.7.4 (from fastapi==0.115.0->-r backend/requirements.txt (line 1))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.1627077Z   Downloading pydantic-2.14.3-py3-none-any.whl.metadata (141 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.1961202Z Collecting typing-extensions>=4.8.0 (from fastapi==0.115.0->-r backend/requirements.txt (line 1))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.2102983Z   Downloading typing_extensions-4.16.0-py3-none-any.whl.metadata (3.3 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.2316578Z Collecting click>=7.0 (from uvicorn==0.30.6->uvicorn[standard]==0.30.6->-r backend/requirements.txt (line 2))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.2399698Z   Downloading click-8.5.1-py3-none-any.whl.metadata (2.6 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.2594164Z Collecting h11>=0.8 (from uvicorn==0.30.6->uvicorn[standard]==0.30.6->-r backend/requirements.txt (line 2))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.2663901Z   Downloading h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.3867175Z Collecting greenlet!=0.4.17 (from sqlalchemy==2.0.35->-r backend/requirements.txt (line 4))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.3952363Z   Downloading greenlet-3.5.6-cp312-cp312-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl.metadata (3.8 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.4372479Z Collecting python-dotenv>=0.21.0 (from pydantic-settings==2.5.2->-r backend/requirements.txt (line 5))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.4448364Z   Downloading python_dotenv-1.2.4-py3-none-any.whl.metadata (29 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.4715875Z Collecting ecdsa!=0.15 (from python-jose==3.5.0->python-jose[cryptography]==3.5.0->-r backend/requirements.txt (line 6))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.4796550Z   Downloading ecdsa-0.19.2-py2.py3-none-any.whl.metadata (29 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.4998322Z Collecting rsa!=4.1.1,!=4.4,<5.0,>=4.0 (from python-jose==3.5.0->python-jose[cryptography]==3.5.0->-r backend/requirements.txt (line 6))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.5063220Z   Downloading rsa-4.9.1-py3-none-any.whl.metadata (5.6 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.5280424Z Collecting pyasn1>=0.5.0 (from python-jose==3.5.0->python-jose[cryptography]==3.5.0->-r backend/requirements.txt (line 6))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.5346616Z   Downloading pyasn1-0.6.5-py3-none-any.whl.metadata (8.4 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.5530514Z Collecting absl-py>=2.0.0 (from ortools==9.10.4067->-r backend/requirements.txt (line 13))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.5595227Z   Downloading absl_py-2.5.1-py3-none-any.whl.metadata (3.3 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.7237415Z Collecting numpy>=1.13.3 (from ortools==9.10.4067->-r backend/requirements.txt (line 13))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.7307563Z   Downloading numpy-2.5.4-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl.metadata (6.6 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.8506778Z Collecting pandas>=2.0.0 (from ortools==9.10.4067->-r backend/requirements.txt (line 13))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.8592955Z   Downloading pandas-3.1.1-cp312-cp312-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl.metadata (16 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.9717809Z Collecting protobuf>=5.26.1 (from ortools==9.10.4067->-r backend/requirements.txt (line 13))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.9792123Z   Downloading protobuf-7.36.2-cp310-abi3-manylinux2014_x86_64.whl.metadata (595 bytes)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:27.9926769Z Collecting immutabledict>=3.0.0 (from ortools==9.10.4067->-r backend/requirements.txt (line 13))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.0010368Z   Downloading immutabledict-4.3.1-py3-none-any.whl.metadata (3.5 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.0159327Z Collecting dnspython>=2.0.0 (from email-validator==2.2.0->-r backend/requirements.txt (line 15))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.0344404Z   Downloading dnspython-2.9.2-py3-none-any.whl.metadata (5.8 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.0500897Z Collecting idna>=2.0.0 (from email-validator==2.2.0->-r backend/requirements.txt (line 15))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.0592204Z   Downloading idna-3.20-py3-none-any.whl.metadata (7.2 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.0779591Z Collecting Mako (from alembic==1.20.1->-r backend/requirements.txt (line 16))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.0862099Z   Downloading mako-1.4.3-py3-none-any.whl.metadata (2.9 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.1104121Z Collecting iniconfig (from pytest==8.3.3->-r backend/requirements.txt (line 18))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.1178082Z   Downloading iniconfig-2.3.1-py3-none-any.whl.metadata (2.8 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.1453698Z Collecting packaging (from pytest==8.3.3->-r backend/requirements.txt (line 18))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.1531543Z   Downloading packaging-26.3-py3-none-any.whl.metadata (3.5 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.1668092Z Collecting pluggy<2,>=1.5 (from pytest==8.3.3->-r backend/requirements.txt (line 18))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.1739458Z   Downloading pluggy-1.7.0-py3-none-any.whl.metadata (5.0 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.2003377Z Collecting anyio (from httpx==0.27.2->-r backend/requirements.txt (line 20))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.2075870Z   Downloading anyio-4.16.0-py3-none-any.whl.metadata (4.7 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.2288488Z Collecting certifi (from httpx==0.27.2->-r backend/requirements.txt (line 20))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.2369262Z   Downloading certifi-2026.10.23-py3-none-any.whl.metadata (2.5 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.2635547Z Collecting httpcore==1.* (from httpx==0.27.2->-r backend/requirements.txt (line 20))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.2717415Z   Downloading httpcore-1.0.9-py3-none-any.whl.metadata (21 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.2907865Z Collecting sniffio (from httpx==0.27.2->-r backend/requirements.txt (line 20))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.2988833Z   Downloading sniffio-1.3.1-py3-none-any.whl.metadata (3.9 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.4213632Z Collecting psycopg-binary==3.3.8 (from psycopg[binary]==3.3.8->-r backend/requirements.txt (line 14))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.4281537Z   Downloading psycopg_binary-3.3.8-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (2.7 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.5912977Z Collecting cryptography>=3.4.0 (from python-jose[cryptography]==3.5.0->-r backend/requirements.txt (line 6))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.6015679Z   Downloading cryptography-50.0.2-cp311-abi3-manylinux_2_34_x86_64.whl.metadata (4.4 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.6340452Z Collecting httptools>=0.5.0 (from uvicorn[standard]==0.30.6->-r backend/requirements.txt (line 2))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.6410301Z   Downloading httptools-0.9.0-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (3.5 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.6761981Z Collecting pyyaml>=5.1 (from uvicorn[standard]==0.30.6->-r backend/requirements.txt (line 2))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.6830725Z   Downloading pyyaml-6.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (2.4 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.7146154Z Collecting uvloop!=0.15.0,!=0.15.1,>=0.14.0 (from uvicorn[standard]==0.30.6->-r backend/requirements.txt (line 2))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.7265029Z   Downloading uvloop-0.23.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (5.1 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.8018240Z Collecting watchfiles>=0.13 (from uvicorn[standard]==0.30.6->-r backend/requirements.txt (line 2))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.8099414Z   Downloading watchfiles-1.3.0-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (4.9 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.9064735Z Collecting websockets>=10.4 (from uvicorn[standard]==0.30.6->-r backend/requirements.txt (line 2))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.9161998Z   Downloading websockets-17.4-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (6.3 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.9394088Z Collecting annotated-types>=0.6.0 (from pydantic!=1.8,!=1.8.1,!=2.0.0,!=2.0.1,!=2.1.0,<3.0.0,>=1.7.4->fastapi==0.115.0->-r backend/requirements.txt (line 1))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:28.9474497Z   Downloading annotated_types-0.8.0-py3-none-any.whl.metadata (15 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:29.4934427Z Collecting pydantic-core==2.50.4 (from pydantic!=1.8,!=1.8.1,!=2.0.0,!=2.0.1,!=2.1.0,<3.0.0,>=1.7.4->fastapi==0.115.0->-r backend/requirements.txt (line 1))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:29.5030206Z   Downloading pydantic_core-2.50.4-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (6.6 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:29.5208865Z Collecting typing-inspection>=0.4.4 (from pydantic!=1.8,!=1.8.1,!=2.0.0,!=2.0.1,!=2.1.0,<3.0.0,>=1.7.4->fastapi==0.115.0->-r backend/requirements.txt (line 1))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:29.5288713Z   Downloading typing_inspection-0.4.5-py3-none-any.whl.metadata (2.6 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:29.6132062Z Collecting cffi>=2.0.0 (from cryptography>=3.4.0->python-jose[cryptography]==3.5.0->-r backend/requirements.txt (line 6))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:29.6204046Z   Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (2.5 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:29.6359288Z Collecting pycparser (from cffi>=2.0.0->cryptography>=3.4.0->python-jose[cryptography]==3.5.0->-r backend/requirements.txt (line 6))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:29.6424768Z   Downloading pycparser-3.12-py3-none-any.whl.metadata (9.7 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:29.6593671Z Collecting six>=1.9.0 (from ecdsa!=0.15->python-jose==3.5.0->python-jose[cryptography]==3.5.0->-r backend/requirements.txt (line 6))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:29.7029800Z   Downloading six-1.17.0-py2.py3-none-any.whl.metadata (1.7 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:29.7228618Z Collecting python-dateutil>=2.9.0 (from pandas>=2.0.0->ortools==9.10.4067->-r backend/requirements.txt (line 13))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:29.7311219Z   Downloading python_dateutil-4.0.0-py3-none-any.whl.metadata (7.3 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.0617101Z Collecting tzdata (from python-dateutil>=2.9.0->pandas>=2.0.0->ortools==9.10.4067->-r backend/requirements.txt (line 13))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.0690588Z   Downloading tzdata-2026.6-py2.py3-none-any.whl.metadata (1.4 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.1201571Z Collecting MarkupSafe>=2.0 (from Mako->alembic==1.20.1->-r backend/requirements.txt (line 16))
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.1267933Z   Downloading markupsafe-3.0.4-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (2.7 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.1386826Z Downloading fastapi-0.115.0-py3-none-any.whl (94 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.1472347Z Downloading uvicorn-0.30.6-py3-none-any.whl (62 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.1571754Z Downloading sqlmodel-0.0.15-py3-none-any.whl (25 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.1726768Z Downloading SQLAlchemy-2.0.35-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (3.2 MB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.2262492Z    ÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöü 3.2/3.2 MB 66.7 MB/s  0:00:00
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.2332674Z Downloading pydantic_settings-2.5.2-py3-none-any.whl (26 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.2440680Z Downloading python_jose-3.5.0-py2.py3-none-any.whl (34 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.2529135Z Downloading passlib-1.7.4-py2.py3-none-any.whl (525 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.2711705Z    ÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöü 525.6/525.6 kB 16.2 MB/s  0:00:00
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.2781627Z Downloading bcrypt-4.0.1-cp36-abi3-manylinux_2_28_x86_64.whl (593 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.2842405Z    ÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöü 593.7/593.7 kB 88.0 MB/s  0:00:00
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.2921158Z Downloading python_multipart-0.0.9-py3-none-any.whl (22 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:30.3018433Z Downloading ortools-9.10.4067-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (26.7 MB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.0037697Z    ÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöü 26.7/26.7 MB 37.8 MB/s  0:00:00
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.0100688Z Downloading psycopg-3.3.8-py3-none-any.whl (216 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.0183730Z Downloading email_validator-2.2.0-py3-none-any.whl (33 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.0273693Z Downloading alembic-1.20.1-py3-none-any.whl (270 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.0366888Z Downloading ruff-0.17.4-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (10.6 MB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.1699041Z    ÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöü 10.6/10.6 MB 78.9 MB/s  0:00:00
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.1766341Z Downloading pytest-8.3.3-py3-none-any.whl (342 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.1879620Z Downloading pytest_asyncio-0.24.0-py3-none-any.whl (18 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.1965003Z Downloading httpx-0.27.2-py3-none-any.whl (76 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.2048208Z Downloading psycopg_binary-3.3.8-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (5.2 MB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.2654897Z    ÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöü 5.2/5.2 MB 85.6 MB/s  0:00:00
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.2724348Z Downloading httpcore-1.0.9-py3-none-any.whl (78 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.2820181Z Downloading pluggy-1.7.0-py3-none-any.whl (27 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.2905759Z Downloading pydantic-2.14.3-py3-none-any.whl (494 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.2994299Z Downloading pydantic_core-2.50.4-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (2.3 MB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.3242744Z    ÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöü 2.3/2.3 MB 87.5 MB/s  0:00:00
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.3322617Z Downloading rsa-4.9.1-py3-none-any.whl (34 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.3405524Z Downloading starlette-0.38.6-py3-none-any.whl (71 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.3525082Z Downloading anyio-4.16.0-py3-none-any.whl (134 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.3613336Z Downloading absl_py-2.5.1-py3-none-any.whl (137 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.3703346Z Downloading annotated_types-0.8.0-py3-none-any.whl (13 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.3787826Z Downloading click-8.5.1-py3-none-any.whl (126 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.3878244Z Downloading cryptography-50.0.2-cp311-abi3-manylinux_2_34_x86_64.whl (4.8 MB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.4474034Z    ÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöü 4.8/4.8 MB 78.3 MB/s  0:00:00
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.4551590Z Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (221 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.4678152Z Downloading dnspython-2.9.2-py3-none-any.whl (360 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.4793583Z Downloading ecdsa-0.19.2-py2.py3-none-any.whl (150 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.4916627Z Downloading greenlet-3.5.6-cp312-cp312-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl (621 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.4982875Z    ÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöü 621.4/621.4 kB 85.4 MB/s  0:00:00
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.5055560Z Downloading h11-0.16.0-py3-none-any.whl (37 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.5141462Z Downloading httptools-0.9.0-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (552 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.5185800Z    ÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöü 552.8/552.8 kB 117.3 MB/s  0:00:00
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.5251226Z Downloading idna-3.20-py3-none-any.whl (69 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.5337397Z Downloading immutabledict-4.3.1-py3-none-any.whl (5.0 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.5426461Z Downloading numpy-2.5.4-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl (16.7 MB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.7507532Z    ÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöü 16.7/16.7 MB 80.4 MB/s  0:00:00
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.7569549Z Downloading pandas-3.1.1-cp312-cp312-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl (12.0 MB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.8993172Z    ÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöü 12.0/12.0 MB 84.2 MB/s  0:00:00
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.9075333Z Downloading protobuf-7.36.2-cp310-abi3-manylinux2014_x86_64.whl (343 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.9175059Z Downloading pyasn1-0.6.5-py3-none-any.whl (84 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.9293080Z Downloading python_dateutil-4.0.0-py3-none-any.whl (92 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.9405227Z Downloading python_dotenv-1.2.4-py3-none-any.whl (23 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.9492801Z Downloading pyyaml-6.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (807 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.9552344Z    ÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöü 807.9/807.9 kB 151.9 MB/s  0:00:00
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.9619328Z Downloading six-1.17.0-py2.py3-none-any.whl (11 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.9705235Z Downloading typing_extensions-4.16.0-py3-none-any.whl (45 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.9789644Z Downloading typing_inspection-0.4.5-py3-none-any.whl (14 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:31.9880975Z Downloading uvloop-0.23.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (4.5 MB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:32.0375010Z    ÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöüÔöü 4.5/4.5 MB 90.5 MB/s  0:00:00
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:32.0468007Z Downloading watchfiles-1.3.0-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (458 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:32.0598215Z Downloading websockets-17.4-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (226 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:32.0689795Z Downloading certifi-2026.10.23-py3-none-any.whl (135 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:32.0774923Z Downloading iniconfig-2.3.1-py3-none-any.whl (7.6 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:32.0855732Z Downloading mako-1.4.3-py3-none-any.whl (80 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:32.0948461Z Downloading markupsafe-3.0.4-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (22 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:32.1035043Z Downloading packaging-26.3-py3-none-any.whl (129 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:32.1120345Z Downloading pycparser-3.12-py3-none-any.whl (62 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:32.1201499Z Downloading sniffio-1.3.1-py3-none-any.whl (10 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:32.1287244Z Downloading tzdata-2026.6-py2.py3-none-any.whl (348 kB)
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:32.4402128Z Installing collected packages: passlib, websockets, uvloop, tzdata, typing-extensions, sniffio, six, ruff, pyyaml, python-multipart, python-dotenv, pycparser, pyasn1, psycopg-binary, protobuf, pluggy, packaging, numpy, MarkupSafe, iniconfig, immutabledict, idna, httptools, h11, greenlet, dnspython, click, certifi, bcrypt, annotated-types, absl-py, uvicorn, typing-inspection, sqlalchemy, rsa, python-dateutil, pytest, pydantic-core, psycopg, Mako, httpcore, email-validator, ecdsa, cffi, anyio, watchfiles, starlette, python-jose, pytest-asyncio, pydantic, pandas, httpx, cryptography, alembic, sqlmodel, pydantic-settings, ortools, fastapi
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:44.2508785Z 
Backend (lint + test)	Run pip install -r backend/requirements.txt	2026-11-11T00:51:44.2547186Z Successfully installed Mako-1.4.3 MarkupSafe-3.0.4 absl-py-2.5.1 alembic-1.20.1 annotated-types-0.8.0 anyio-4.16.0 bcrypt-4.0.1 certifi-2026.10.23 cffi-2.1.1 click-8.5.1 cryptography-50.0.2 dnspython-2.9.2 ecdsa-0.19.2 email-validator-2.2.0 fastapi-0.115.0 greenlet-3.5.6 h11-0.16.0 httpcore-1.0.9 httptools-0.9.0 httpx-0.27.2 idna-3.20 immutabledict-4.3.1 iniconfig-2.3.1 numpy-2.5.4 ortools-9.10.4067 packaging-26.3 pandas-3.1.1 passlib-1.7.4 pluggy-1.7.0 protobuf-7.36.2 psycopg-3.3.8 psycopg-binary-3.3.8 pyasn1-0.6.5 pycparser-3.12 pydantic-2.14.3 pydantic-core-2.50.4 pydantic-settings-2.5.2 pytest-8.3.3 pytest-asyncio-0.24.0 python-dateutil-4.0.0 python-dotenv-1.2.4 python-jose-3.5.0 python-multipart-0.0.9 pyyaml-6.0.3 rsa-4.9.1 ruff-0.17.4 six-1.17.0 sniffio-1.3.1 sqlalchemy-2.0.35 sqlmodel-0.0.15 starlette-0.38.6 typing-extensions-4.16.0 typing-inspection-0.4.5 tzdata-2026.6 uvicorn-0.30.6 uvloop-0.23.0 watchfiles-1.3.0 websockets-17.4
Backend (lint + test)	Lint (Ruff)	´╗┐2026-11-11T00:51:44.4227931Z ##[group]Run cd backend && ruff check .
Backend (lint + test)	Lint (Ruff)	2026-11-11T00:51:44.4228218Z ^[[36;1mcd backend && ruff check .^[[0m
Backend (lint + test)	Lint (Ruff)	2026-11-11T00:51:44.4275384Z shell: /usr/bin/bash -e {0}
Backend (lint + test)	Lint (Ruff)	2026-11-11T00:51:44.4275598Z env:
Backend (lint + test)	Lint (Ruff)	2026-11-11T00:51:44.4275815Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Lint (Ruff)	2026-11-11T00:51:44.4276352Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.16/x64/lib/pkgconfig
Backend (lint + test)	Lint (Ruff)	2026-11-11T00:51:44.4276702Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Lint (Ruff)	2026-11-11T00:51:44.4277002Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Lint (Ruff)	2026-11-11T00:51:44.4277306Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Lint (Ruff)	2026-11-11T00:51:44.4277598Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.16/x64/lib
Backend (lint + test)	Lint (Ruff)	2026-11-11T00:51:44.4277855Z ##[endgroup]
Backend (lint + test)	Lint (Ruff)	2026-11-11T00:51:44.4496899Z All checks passed!
Backend (lint + test)	Test (pytest)	´╗┐2026-11-11T00:51:44.4528953Z ##[group]Run cd backend && pytest -q
Backend (lint + test)	Test (pytest)	2026-11-11T00:51:44.4529226Z ^[[36;1mcd backend && pytest -q^[[0m
Backend (lint + test)	Test (pytest)	2026-11-11T00:51:44.4572080Z shell: /usr/bin/bash -e {0}
Backend (lint + test)	Test (pytest)	2026-11-11T00:51:44.4572298Z env:
Backend (lint + test)	Test (pytest)	2026-11-11T00:51:44.4572519Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Test (pytest)	2026-11-11T00:51:44.4572880Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.16/x64/lib/pkgconfig
Backend (lint + test)	Test (pytest)	2026-11-11T00:51:44.4573213Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Test (pytest)	2026-11-11T00:51:44.4573507Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Test (pytest)	2026-11-11T00:51:44.4573801Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.16/x64
Backend (lint + test)	Test (pytest)	2026-11-11T00:51:44.4574102Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.16/x64/lib
Backend (lint + test)	Test (pytest)	2026-11-11T00:51:44.4574355Z ##[endgroup]
Backend (lint + test)	Test (pytest)	2026-11-11T00:52:06.9907845Z ........................................................................ [ 63%]
Backend (lint + test)	Test (pytest)	2026-11-11T00:52:10.8005742Z .........................................                                [100%]
Backend (lint + test)	Test (pytest)	2026-11-11T00:52:10.8006836Z =============================== warnings summary ===============================
Backend (lint + test)	Test (pytest)	2026-11-11T00:52:10.8007872Z ../../../../../../opt/hostedtoolcache/Python/3.12.16/x64/lib/python3.12/site-packages/passlib/utils/__init__.py:854
Backend (lint + test)	Test (pytest)	2026-11-11T00:52:10.8009202Z   /opt/hostedtoolcache/Python/3.12.16/x64/lib/python3.12/site-packages/passlib/utils/__init__.py:854: DeprecationWarning: 'crypt' is deprecated and slated for removal in Python 3.13
Backend (lint + test)	Test (pytest)	2026-11-11T00:52:10.8010559Z     from crypt import crypt as _crypt
Backend (lint + test)	Test (pytest)	2026-11-11T00:52:10.8010909Z 
Backend (lint + test)	Test (pytest)	2026-11-11T00:52:10.8011399Z ../../../../../../opt/hostedtoolcache/Python/3.12.16/x64/lib/python3.12/site-packages/starlette/testclient.py:40
Backend (lint + test)	Test (pytest)	2026-11-11T00:52:10.8012821Z   /opt/hostedtoolcache/Python/3.12.16/x64/lib/python3.12/site-packages/starlette/testclient.py:40: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
Backend (lint + test)	Test (pytest)	2026-11-11T00:52:10.8014204Z     _PortalFactoryType = typing.Callable[[], typing.ContextManager[anyio.abc.BlockingPortal]]
Backend (lint + test)	Test (pytest)	2026-11-11T00:52:10.8014778Z 
Backend (lint + test)	Test (pytest)	2026-11-11T00:52:10.8015161Z -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
Backend (lint + test)	Test (pytest)	2026-11-11T00:52:10.8015770Z 113 passed, 2 warnings in 23.96s
Backend (lint + test)	Post Run actions/setup-python@v5	´╗┐2026-11-11T00:52:11.0716569Z Post job cleanup.
Backend (lint + test)	Post Run actions/setup-python@v5	2026-11-11T00:52:11.1788975Z (node:2230) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
Backend (lint + test)	Post Run actions/setup-python@v5	2026-11-11T00:52:11.1790086Z (Use `node --trace-deprecation ...` to show where the warning was created)
Backend (lint + test)	Post Run actions/checkout@v4	´╗┐2026-11-11T00:52:11.2011666Z Post job cleanup.
Backend (lint + test)	Post Run actions/checkout@v4	2026-11-11T00:52:11.2848000Z [command]/usr/bin/git version
Backend (lint + test)	Post Run actions/checkout@v4	2026-11-11T00:52:11.2911131Z git version 2.56.0
Backend (lint + test)	Post Run actions/checkout@v4	2026-11-11T00:52:11.2958864Z Temporarily overriding HOME='/home/runner/work/_temp/9f5e183e-fc35-4d41-9c29-96ed6d2b0bea' before making global git config changes
Backend (lint + test)	Post Run actions/checkout@v4	2026-11-11T00:52:11.2959985Z Adding repository directory to the temporary git global config as a safe directory
Backend (lint + test)	Post Run actions/checkout@v4	2026-11-11T00:52:11.2960994Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/fairschedule-ai/fairschedule-ai
Backend (lint + test)	Post Run actions/checkout@v4	2026-11-11T00:52:11.3050539Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
Backend (lint + test)	Post Run actions/checkout@v4	2026-11-11T00:52:11.3126803Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
Backend (lint + test)	Post Run actions/checkout@v4	2026-11-11T00:52:11.3569399Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
Backend (lint + test)	Post Run actions/checkout@v4	2026-11-11T00:52:11.3599724Z http.https://github.com/.extraheader
Backend (lint + test)	Post Run actions/checkout@v4	2026-11-11T00:52:11.3616811Z [command]/usr/bin/git config --local --unset-all http.https://github.com/.extraheader
Backend (lint + test)	Post Run actions/checkout@v4	2026-11-11T00:52:11.3707368Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
Backend (lint + test)	Post Run actions/checkout@v4	2026-11-11T00:52:11.4137055Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
Backend (lint + test)	Post Run actions/checkout@v4	2026-11-11T00:52:11.4236921Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
Backend (lint + test)	Complete job	´╗┐2026-11-11T00:52:11.4738238Z Cleaning up orphan processes
Backend (lint + test)	Complete job	2026-11-11T00:52:11.5075367Z ##[warning]Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/setup-python@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
Frontend (lint + test + build)	Set up job	´╗┐2026-11-11T00:51:20.6327642Z Current runner version: '2.338.2'
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6365607Z ##[group]Runner Image Provisioner
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6367057Z Hosted Compute Agent
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6367952Z Version: 20261028.624
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6369061Z Commit: 54898b74c23fde5556c9b3c3a2290865feef0dfe
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6370190Z Build Date: 2026-10-28T21:51:42Z
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6371784Z Worker ID: {0a87dfdc-73a5-4b91-b7f6-34a29273eb76}
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6372949Z Region: northcentralus
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6373842Z Cloud: Azure
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6374758Z ##[endgroup]
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6376894Z ##[group]Operating System
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6378072Z Ubuntu
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6378928Z 26.04.1
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6379739Z LTS
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6380882Z ##[endgroup]
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6381767Z ##[group]Runner Image
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6382733Z Image: ubuntu-26.04
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6383774Z Version: 20261101.186.1
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6385494Z Included Software: https://github.com/actions/runner-images/blob/ubuntu26/20261101.186/images/ubuntu/Ubuntu2604-Readme.md
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6388461Z Image Release: https://github.com/actions/runner-images/releases/tag/ubuntu26%2F20261101.186
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6390083Z ##[endgroup]
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6392521Z ##[group]GITHUB_TOKEN Permissions
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6395686Z Contents: read
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6396794Z Metadata: read
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6397739Z Packages: read
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6398762Z ##[endgroup]
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6402022Z Secret source: Actions
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6403526Z Cache mode: write
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.6404968Z Prepare workflow directory
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.7105604Z Prepare all required actions
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.7256818Z Getting action download info
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:20.9865191Z Download action repository 'actions/checkout@v4' (SHA:11d5960a326750d5838078e36cf38b85af677262)
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:21.1353688Z Download action repository 'actions/setup-node@v4' (SHA:49933ea5288caeca8642d1e84afbd3f7d6820020)
Frontend (lint + test + build)	Set up job	2026-11-11T00:51:21.3223538Z Complete job name: Frontend (lint + test + build)
Frontend (lint + test + build)	Run actions/checkout@v4	´╗┐2026-11-11T00:51:21.4095571Z ##[group]Run actions/checkout@v4
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4096447Z with:
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4096920Z   repository: M-A-E-A/fairschedule-ai
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4101246Z   token: ***
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4101867Z   ssh-strict: true
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4102488Z   ssh-user: git
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4103094Z   persist-credentials: true
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4103789Z   clean: true
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4104514Z   sparse-checkout-cone-mode: true
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4105330Z   fetch-depth: 1
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4106024Z   fetch-tags: false
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4106752Z   show-progress: true
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4107412Z   lfs: false
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4108024Z   submodules: false
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4108578Z   set-safe-directory: true
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4109114Z   allow-unsafe-pr-checkout: false
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.4110086Z ##[endgroup]
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.6637784Z Syncing repository: M-A-E-A/fairschedule-ai
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.6640678Z ##[group]Getting Git version info
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.6641939Z Working directory is '/home/runner/work/fairschedule-ai/fairschedule-ai'
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.6643714Z [command]/usr/bin/git version
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.6650254Z git version 2.56.0
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.6655807Z ##[endgroup]
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.6693287Z Temporarily overriding HOME='/home/runner/work/_temp/9a60e62f-2f91-4471-976a-22ffbe5c5ffa' before making global git config changes
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.6711541Z Adding repository directory to the temporary git global config as a safe directory
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.6713787Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/fairschedule-ai/fairschedule-ai
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8281654Z Deleting the contents of '/home/runner/work/fairschedule-ai/fairschedule-ai'
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8283833Z ##[group]Initializing the repository
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8302647Z [command]/usr/bin/git init /home/runner/work/fairschedule-ai/fairschedule-ai
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8304547Z hint: Using 'master' as the name for the initial branch. This default branch name
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8306816Z hint: will change to "main" in Git 3.0. To configure the initial branch name
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8308324Z hint: to use in all of your new repositories, which will suppress this warning,
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8309579Z hint: call:
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8310938Z hint:
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8311884Z hint: 	git config --global init.defaultBranch <name>
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8312951Z hint:
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8313960Z hint: Names commonly chosen instead of 'master' are 'main', 'trunk' and
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8315522Z hint: 'development'. The just-created branch can be renamed via this command:
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8316775Z hint:
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8321152Z hint: 	git branch -m <name>
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8322163Z hint:
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8323263Z hint: Disable this message with "git config set advice.defaultBranchName false"
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8325038Z Initialized empty Git repository in /home/runner/work/fairschedule-ai/fairschedule-ai/.git/
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8327982Z [command]/usr/bin/git remote add origin https://github.com/M-A-E-A/fairschedule-ai
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8331139Z ##[endgroup]
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8332532Z ##[group]Disabling automatic garbage collection
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8346583Z [command]/usr/bin/git config --local gc.auto 0
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8349780Z ##[endgroup]
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8351610Z ##[group]Setting up auth
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8352885Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8356649Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8361025Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8365557Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8674621Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.8723735Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.9063560Z [command]/usr/bin/git config --local http.https://github.com/.extraheader AUTHORIZATION: basic ***
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.9113958Z ##[endgroup]
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.9115989Z ##[group]Fetching the repository
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:21.9125306Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +b735b9018ed9218e646ac4d1ff295535523bbe8b:refs/remotes/origin/master
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:22.3190750Z From https://github.com/M-A-E-A/fairschedule-ai
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:22.3193582Z  * [new ref]         b735b9018ed9218e646ac4d1ff295535523bbe8b -> origin/master
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:22.3200159Z ##[endgroup]
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:22.3202163Z ##[group]Determining the checkout info
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:22.3204284Z ##[endgroup]
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:22.3205389Z [command]/usr/bin/git sparse-checkout disable
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:22.3246405Z [command]/usr/bin/git config --local --unset-all extensions.worktreeConfig
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:22.3287083Z ##[group]Checking out the ref
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:22.3293017Z [command]/usr/bin/git checkout --progress --force -B master refs/remotes/origin/master
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:22.3430228Z Reset branch 'master'
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:22.3438708Z branch 'master' set up to track 'origin/master'.
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:22.3446269Z ##[endgroup]
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:22.3496829Z [command]/usr/bin/git log -1 --format=%H
Frontend (lint + test + build)	Run actions/checkout@v4	2026-11-11T00:51:22.3528063Z b735b9018ed9218e646ac4d1ff295535523bbe8b
Frontend (lint + test + build)	Run actions/setup-node@v4	´╗┐2026-11-11T00:51:22.3941454Z ##[group]Run actions/setup-node@v4
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:22.3942797Z with:
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:22.3943714Z   node-version: 24
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:22.3944686Z   cache: npm
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:22.3945824Z   cache-dependency-path: frontend/package-lock.json
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:22.3947540Z   always-auth: false
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:22.3948589Z   check-latest: false
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:22.3958691Z   token: ***
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:22.3959642Z ##[endgroup]
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:22.5816831Z (node:2168) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:22.5832549Z Found in cache @ /opt/hostedtoolcache/node/24.22.2/x64
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:22.5834336Z ##[group]Environment details
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:22.5837725Z (Use `node --trace-deprecation ...` to show where the warning was created)
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:23.1012515Z node: v24.22.2
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:23.1038796Z npm: 11.19.1
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:23.1044623Z yarn: 1.22.22
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:23.1054830Z ##[endgroup]
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:23.1068152Z [command]/opt/hostedtoolcache/node/24.22.2/x64/bin/npm config get cache
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:23.2856788Z /home/runner/.npm
Frontend (lint + test + build)	Run actions/setup-node@v4	2026-11-11T00:51:23.4541289Z npm cache is not found
Frontend (lint + test + build)	Run cd frontend && npm ci	´╗┐2026-11-11T00:51:23.4783928Z ##[group]Run cd frontend && npm ci
Frontend (lint + test + build)	Run cd frontend && npm ci	2026-11-11T00:51:23.4784469Z ^[[36;1mcd frontend && npm ci^[[0m
Frontend (lint + test + build)	Run cd frontend && npm ci	2026-11-11T00:51:23.4851184Z shell: /usr/bin/bash -e {0}
Frontend (lint + test + build)	Run cd frontend && npm ci	2026-11-11T00:51:23.4851591Z ##[endgroup]
Frontend (lint + test + build)	Run cd frontend && npm ci	2026-11-11T00:51:25.9811899Z npm warn deprecated whatwg-encoding@3.1.1: Use @exodus/bytes instead for a more spec-conformant and faster implementation
Frontend (lint + test + build)	Run cd frontend && npm ci	2026-11-11T00:51:30.3349605Z 
Frontend (lint + test + build)	Run cd frontend && npm ci	2026-11-11T00:51:30.3361642Z added 295 packages, and audited 296 packages in 7s
Frontend (lint + test + build)	Run cd frontend && npm ci	2026-11-11T00:51:30.3390692Z 
Frontend (lint + test + build)	Run cd frontend && npm ci	2026-11-11T00:51:30.3411147Z 64 packages are looking for funding
Frontend (lint + test + build)	Run cd frontend && npm ci	2026-11-11T00:51:30.3451054Z   run `npm fund` for details
Frontend (lint + test + build)	Run cd frontend && npm ci	2026-11-11T00:51:30.3653138Z 
Frontend (lint + test + build)	Run cd frontend && npm ci	2026-11-11T00:51:30.3653752Z found 0 vulnerabilities
Frontend (lint + test + build)	Audit (npm)	´╗┐2026-11-11T00:51:30.4336870Z ##[group]Run cd frontend && npm audit --audit-level=high
Frontend (lint + test + build)	Audit (npm)	2026-11-11T00:51:30.4337593Z ^[[36;1mcd frontend && npm audit --audit-level=high^[[0m
Frontend (lint + test + build)	Audit (npm)	2026-11-11T00:51:30.4412273Z shell: /usr/bin/bash -e {0}
Frontend (lint + test + build)	Audit (npm)	2026-11-11T00:51:30.4412710Z ##[endgroup]
Frontend (lint + test + build)	Audit (npm)	2026-11-11T00:51:31.1209810Z found 0 vulnerabilities
Frontend (lint + test + build)	Lint (ESLint)	´╗┐2026-11-11T00:51:31.1419094Z ##[group]Run cd frontend && npm run lint
Frontend (lint + test + build)	Lint (ESLint)	2026-11-11T00:51:31.1419667Z ^[[36;1mcd frontend && npm run lint^[[0m
Frontend (lint + test + build)	Lint (ESLint)	2026-11-11T00:51:31.1491968Z shell: /usr/bin/bash -e {0}
Frontend (lint + test + build)	Lint (ESLint)	2026-11-11T00:51:31.1492402Z ##[endgroup]
Frontend (lint + test + build)	Lint (ESLint)	2026-11-11T00:51:31.3091260Z 
Frontend (lint + test + build)	Lint (ESLint)	2026-11-11T00:51:31.3123082Z > fairschedule-ai-frontend@0.1.0 lint
Frontend (lint + test + build)	Lint (ESLint)	2026-11-11T00:51:31.3162061Z > eslint .
Frontend (lint + test + build)	Lint (ESLint)	2026-11-11T00:51:31.3200914Z 
Frontend (lint + test + build)	Test (Vitest)	´╗┐2026-11-11T00:51:35.5838439Z ##[group]Run cd frontend && npm run test -- --run
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:35.5838858Z ^[[36;1mcd frontend && npm run test -- --run^[[0m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:35.5893899Z shell: /usr/bin/bash -e {0}
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:35.5894230Z ##[endgroup]
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:35.6994704Z 
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:35.6995477Z > fairschedule-ai-frontend@0.1.0 test
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:35.6996392Z > vitest run --run
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:35.6996845Z 
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:36.1211048Z 
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:36.1214333Z ^[[1m^[[30m^[[46m RUN ^[[49m^[[39m^[[22m ^[[36mv5.1.0 ^[[39m^[[90m/home/runner/work/fairschedule-ai/fairschedule-ai/frontend^[[39m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:36.1226131Z 
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:37.7632053Z  ^[[32mÔ£ô^[[39m src/pages/LoginPage.test.tsx ^[[2m(^[[22m^[[2m7 tests^[[22m^[[2m)^[[22m^[[33m 418^[[2mms^[[22m^[[39m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:38.8271678Z  ^[[32mÔ£ô^[[39m src/pages/AdminUsersPage.test.tsx ^[[2m(^[[22m^[[2m2 tests^[[22m^[[2m)^[[22m^[[32m 292^[[2mms^[[22m^[[39m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:39.8746776Z  ^[[32mÔ£ô^[[39m src/pages/RoomsPage.test.tsx ^[[2m(^[[22m^[[2m2 tests^[[22m^[[2m)^[[22m^[[32m 275^[[2mms^[[22m^[[39m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:40.7606600Z  ^[[32mÔ£ô^[[39m src/pages/CampusPage.test.tsx ^[[2m(^[[22m^[[2m2 tests^[[22m^[[2m)^[[22m^[[32m 168^[[2mms^[[22m^[[39m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:41.7288189Z  ^[[32mÔ£ô^[[39m src/components/AppShell.test.tsx ^[[2m(^[[22m^[[2m3 tests^[[22m^[[2m)^[[22m^[[32m 204^[[2mms^[[22m^[[39m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:42.7502017Z  ^[[32mÔ£ô^[[39m src/pages/DashboardPage.test.tsx ^[[2m(^[[22m^[[2m3 tests^[[22m^[[2m)^[[22m^[[32m 243^[[2mms^[[22m^[[39m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:43.7112647Z  ^[[32mÔ£ô^[[39m src/pages/MySchedulePage.test.tsx ^[[2m(^[[22m^[[2m2 tests^[[22m^[[2m)^[[22m^[[32m 184^[[2mms^[[22m^[[39m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:44.6379483Z  ^[[32mÔ£ô^[[39m src/pages/AiPage.test.tsx ^[[2m(^[[22m^[[2m2 tests^[[22m^[[2m)^[[22m^[[32m 161^[[2mms^[[22m^[[39m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:45.6766910Z  ^[[32mÔ£ô^[[39m src/components/RequireRole.test.tsx ^[[2m(^[[22m^[[2m4 tests^[[22m^[[2m)^[[22m^[[32m 269^[[2mms^[[22m^[[39m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:46.6492656Z  ^[[32mÔ£ô^[[39m src/pages/TimetablePage.test.tsx ^[[2m(^[[22m^[[2m2 tests^[[22m^[[2m)^[[22m^[[32m 196^[[2mms^[[22m^[[39m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:47.3635027Z  ^[[32mÔ£ô^[[39m src/components/LottieLoader.test.tsx ^[[2m(^[[22m^[[2m2 tests^[[22m^[[2m)^[[22m^[[32m 93^[[2mms^[[22m^[[39m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:48.2490159Z  ^[[32mÔ£ô^[[39m src/App.test.tsx ^[[2m(^[[22m^[[2m1 test^[[22m^[[2m)^[[22m^[[32m 123^[[2mms^[[22m^[[39m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:48.2717540Z 
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:48.2744975Z ^[[2m Test Files ^[[22m ^[[1m^[[32m12 passed^[[39m^[[22m^[[90m (12)^[[39m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:48.2760220Z ^[[2m      Tests ^[[22m ^[[1m^[[32m32 passed^[[39m^[[22m^[[90m (32)^[[39m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:48.2761501Z ^[[2m   Start at ^[[22m 00:51:36
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:48.2762888Z ^[[2m   Duration ^[[22m 12.14s^[[2m (environment 43%, tests 25%, import 21%, transform 6%, setup 5%, worker 1%)^[[22m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:48.2780869Z 
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:48.2785263Z ^[[2mEnvironment ^[[22m ^[[33mjsdom was created 12 times^[[39m^[[2m ┬À 4.55s total, 43% of tracked time^[[22m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:48.2794260Z ^[[2m            ^[[22m ^[[2mcreate it once per worker with ^[[22m^[[33mpool: 'vmThreads'^[[39m^[[2m (keeps per-file isolation) or ^[[22m^[[33misolate: false^[[39m^[[2m (shares it across files)^[[22m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:48.2796410Z ^[[2m            ^[[22m ^[[2mlearn more: https://vitest.dev/guide/improving-performance#test-environments^[[22m
Frontend (lint + test + build)	Test (Vitest)	2026-11-11T00:51:48.2797252Z 
Frontend (lint + test + build)	Build (Vite)	´╗┐2026-11-11T00:51:48.3209272Z ##[group]Run cd frontend && npm run build
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:48.3209632Z ^[[36;1mcd frontend && npm run build^[[0m
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:48.3265570Z shell: /usr/bin/bash -e {0}
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:48.3265863Z ##[endgroup]
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:48.4421089Z 
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:48.4441584Z > fairschedule-ai-frontend@0.1.0 build
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:48.4448485Z > tsc -b && vite build
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:48.4448910Z 
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:52.6572889Z ^[[36mvite v8.3.7 ^[[32mbuilding client environment for production...^[[36m^[[39m
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:52.6692577Z transforming...
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:52.9800940Z Ô£ô 59 modules transformed.
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.0494247Z rendering chunks...
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2394233Z computing gzip size...
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2647220Z dist/index.html                     0.40 kB Ôöé gzip:   0.26 kB
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2648494Z dist/assets/index-SvLVliAF.css      7.24 kB Ôöé gzip:   2.21 kB
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2649721Z dist/assets/index-BrSS0O_p.js   1,547.58 kB Ôöé gzip: 420.28 kB
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2650521Z 
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2661651Z ^[[33m[plugin builtin:vite-reporter] 
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2662652Z (!) Some chunks are larger than 500 kB after minification. Consider:
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2663754Z - Using dynamic import() to code-split the application
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2665316Z - Use build.rolldownOptions.output.codeSplitting to improve chunking: https://rolldown.rs/reference/OutputOptions.codeSplitting
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2667146Z - Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.^[[39m
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2690740Z ^[[33m^[[33m[EVAL] ^[[0mUse of direct `eval` function is strongly discouraged as it poses security risks and may cause issues with minification.
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2692453Z        ^[[38;5;246mÔò¡^[[0m^[[38;5;246mÔöÇ^[[0m^[[38;5;246m[^[[0m node_modules/lottie-web/build/player/lottie.js:14422:33 ^[[38;5;246m]^[[0m
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2693661Z        ^[[38;5;246mÔöé^[[0m
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2703796Z  ^[[38;5;246m14422 Ôöé^[[0m ^[[38;5;249m ^[[0m^[[38;5;249m ^[[0m^[[38;5;249m ^[[0m^[[38;5;249m ^[[0m^[[38;5;249m ^[[0m^[[38;5;249m ^[[0m^[[38;5;249mv^[[0m^[[38;5;249ma^[[0m^[[38;5;249mr^[[0m^[[38;5;249m ^[[0m^[[38;5;249me^[[0m^[[38;5;249mx^[[0m^[[38;5;249mp^[[0m^[[38;5;249mr^[[0m^[[38;5;249me^[[0m^[[38;5;249ms^[[0m^[[38;5;249ms^[[0m^[[38;5;249mi^[[0m^[[38;5;249mo^[[0m^[[38;5;249mn^[[0m^[[38;5;249m_^[[0m^[[38;5;249mf^[[0m^[[38;5;249mu^[[0m^[[38;5;249mn^[[0m^[[38;5;249mc^[[0m^[[38;5;249mt^[[0m^[[38;5;249mi^[[0m^[[38;5;249mo^[[0m^[[38;5;249mn^[[0m^[[38;5;249m ^[[0m^[[38;5;249m=^[[0m^[[38;5;249m ^[[0meval^[[38;5;249m(^[[0m^[[38;5;249m'^[[0m^[[38;5;249m[^[[0m^[[38;5;249mf^[[0m^[[38;5;249mu^[[0m^[[38;5;249mn^[[0m^[[38;5;249mc^[[0m^[[38;5;249mt^[[0m^[[38;5;249mi^[[0m^[[38;5;249mo^[[0m^[[38;5;249mn^[[0m^[[38;5;249m ^[[0m^[[38;5;249m_^[[0m^[[38;5;249me^[[0m^[[38;5;249mx^[[0m^[[38;5;249mp^[[0m^[[38;5;249mr^[[0m^[[38;5;249me^[[0m^[[38;5;249ms^[[0m^[[38;5;249ms^[[0m^[[38;5;249mi^[[0m^[[38;5;249mo^[[0m^[[38;5;249mn^[[0m^[[38;5;249m_^[[0m^[[38;5;249mf^[[0m^[[38;5;249mu^[[0m^[[38;5;249mn^[[0m^[[38;5;249mc^[[0m^[[38;5;249mt^[[0m^[[38;5;249mi^[[0m^[[38;5;249mo^[[0m^[[38;5;249mn^[[0m^[[38;5;249m(^[[0m^[[38;5;249m)^[[0m^[[38;5;249m{^[[0m^[[38;5;249m'^[[0m^[[38;5;249m ^[[0m^[[38;5;249m+^[[0m^[[38;5;249m ^[[0m^[[38;5;249mv^[[0m^[[38;5;249ma^[[0m^[[38;5;249ml^[[0m^[[38;5;249m ^[[0m^[[38;5;249m+^[[0m^[[38;5;249m ^[[0m^[[38;5;249m'^[[0m^[[38;5;249m;^[[0m^[[38;5;249ms^[[0m^[[38;5;249mc^[[0m^[[38;5;249mo^[[0m^[[38;5;249mp^[[0m^[[38;5;249me^[[0m^[[38;5;249md^[[0m^[[38;5;249m_^[[0m^[[38;5;249mb^[[0m^[[38;5;249mm^[[0m^[[38;5;249m_^[[0m^[[38;5;249mr^[[0m^[[38;5;249mt^[[0m^[[38;5;249m=^[[0m^[[38;5;249m$^[[0m^[[38;5;249mb^[[0m^[[38;5;249mm^[[0m^[[38;5;249m_^[[0m^[[38;5;249mr^[[0m^[[38;5;249mt^[[0m^[[38;5;249m}^[[0m^[[38;5;249m]^[[0m^[[38;5;249m'^[[0m^[[38;5;249m)^[[0m^[[38;5;249m[^[[0m^[[38;5;249m0^[[0m^[[38;5;249m]^[[0m^[[38;5;249m;^[[0m^[[38;5;249m ^[[0m^[[38;5;249m/^[[0m^[[38;5;249m/^[[0m^[[38;5;249m ^[[0m^[[38;5;249me^[[0m^[[38;5;249ms^[[0m^[[38;5;249ml^[[0m^[[38;5;249mi^[[0m^[[38;5;249mn^[[0m^[[38;5;249mt^[[0m^[[38;5;249m-^[[0m^[[38;5;249md^[[0m^[[38;5;249mi^[[0m^[[38;5;249ms^[[0m^[[38;5;249ma^[[0m^[[38;5;249mb^[[0m^[[38;5;249ml^[[0m^[[38;5;249me^[[0m^[[38;5;249m-^[[0m^[[38;5;249ml^[[0m^[[38;5;249mi^[[0m^[[38;5;249mn^[[0m^[[38;5;249me^[[0m^[[38;5;249m ^[[0m^[[38;5;249mn^[[0m^[[38;5;249mo^[[0m^[[38;5;249m-^[[0m^[[38;5;249me^[[0m^[[38;5;249mv^[[0m^[[38;5;249ma^[[0m^[[38;5;249ml^[[0m
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2709728Z ^[[32mÔ£ô built in 612ms^[[39m
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2713102Z  ^[[38;5;240m      Ôöé^[[0m                                 ÔöÇÔöÇÔö¼ÔöÇ  
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2714277Z  ^[[38;5;240m      Ôöé^[[0m                                   Ôò░ÔöÇÔöÇÔöÇ Use of direct `eval` here.
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2715209Z  ^[[38;5;240m      Ôöé^[[0m 
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2716931Z  ^[[38;5;240m      Ôöé^[[0m ^[[38;5;115mHelp^[[0m: Consider using indirect eval. For more information, check the documentation: https://rolldown.rs/guide/troubleshooting#avoiding-direct-eval
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2721202Z ^[[38;5;246mÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔò»^[[0m
Frontend (lint + test + build)	Build (Vite)	2026-11-11T00:51:53.2721774Z ^[[39m
Frontend (lint + test + build)	Post Run actions/setup-node@v4	´╗┐2026-11-11T00:51:53.3155078Z Post job cleanup.
Frontend (lint + test + build)	Post Run actions/setup-node@v4	2026-11-11T00:51:53.4488973Z (node:2446) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
Frontend (lint + test + build)	Post Run actions/setup-node@v4	2026-11-11T00:51:53.4491134Z (Use `node --trace-deprecation ...` to show where the warning was created)
Frontend (lint + test + build)	Post Run actions/setup-node@v4	2026-11-11T00:51:53.4921548Z [command]/usr/bin/tar --posix -cf cache.tzst --exclude cache.tzst -P -C /home/runner/work/fairschedule-ai/fairschedule-ai --files-from manifest.txt --use-compress-program zstdmt
Frontend (lint + test + build)	Post Run actions/setup-node@v4	2026-11-11T00:51:53.9146606Z (node:2446) [DEP0169] DeprecationWarning: `url.parse()` behavior is not standardized and prone to errors that have security implications. Use the WHATWG URL API instead. CVEs are not issued for `url.parse()` vulnerabilities.
Frontend (lint + test + build)	Post Run actions/setup-node@v4	2026-11-11T00:51:54.9049384Z Sent 47575749 of 47575749 (100.0%), 45.4 MBs/sec
Frontend (lint + test + build)	Post Run actions/setup-node@v4	2026-11-11T00:51:55.2562159Z Cache saved with the key: node-cache-Linux-x64-npm-af934aa365679fb935f2d861077c0484bb6a9ab51aabb8f13d3dd7cba69aa77d
Frontend (lint + test + build)	Post Run actions/checkout@v4	´╗┐2026-11-11T00:51:55.2791327Z Post job cleanup.
Frontend (lint + test + build)	Post Run actions/checkout@v4	2026-11-11T00:51:55.3787874Z [command]/usr/bin/git version
Frontend (lint + test + build)	Post Run actions/checkout@v4	2026-11-11T00:51:55.3846121Z git version 2.56.0
Frontend (lint + test + build)	Post Run actions/checkout@v4	2026-11-11T00:51:55.3924083Z Temporarily overriding HOME='/home/runner/work/_temp/84e1e7cc-11cc-4f3b-b46e-8aff77871ab7' before making global git config changes
Frontend (lint + test + build)	Post Run actions/checkout@v4	2026-11-11T00:51:55.3926221Z Adding repository directory to the temporary git global config as a safe directory
Frontend (lint + test + build)	Post Run actions/checkout@v4	2026-11-11T00:51:55.3927740Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/fairschedule-ai/fairschedule-ai
Frontend (lint + test + build)	Post Run actions/checkout@v4	2026-11-11T00:51:55.4037099Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
Frontend (lint + test + build)	Post Run actions/checkout@v4	2026-11-11T00:51:55.4069997Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
Frontend (lint + test + build)	Post Run actions/checkout@v4	2026-11-11T00:51:55.4651981Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
Frontend (lint + test + build)	Post Run actions/checkout@v4	2026-11-11T00:51:55.4663713Z http.https://github.com/.extraheader
Frontend (lint + test + build)	Post Run actions/checkout@v4	2026-11-11T00:51:55.4711257Z [command]/usr/bin/git config --local --unset-all http.https://github.com/.extraheader
Frontend (lint + test + build)	Post Run actions/checkout@v4	2026-11-11T00:51:55.4754256Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
Frontend (lint + test + build)	Post Run actions/checkout@v4	2026-11-11T00:51:55.5399049Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
Frontend (lint + test + build)	Post Run actions/checkout@v4	2026-11-11T00:51:55.5486066Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
Frontend (lint + test + build)	Complete job	´╗┐2026-11-11T00:51:55.6001356Z Cleaning up orphan processes
Frontend (lint + test + build)	Complete job	2026-11-11T00:51:55.6373028Z ##[warning]Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/setup-node@v4. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
```

## 8. Failure summary

**All checks pass on `b735b90`, locally and in CI, and the two agree:**

- Backend: Ruff `All checks passed!`; pytest **113 passed** locally and **113
  passed** in CI (run `42934586787`).
- Frontend: ESLint clean; Vitest **12 files / 32 tests passed** locally and the same
  **12 files / 32 tests** in CI; `npm audit --audit-level=high` → `found 0
  vulnerabilities` locally and in CI; `tsc -b && vite build` succeeded with the
  identical asset hashes `dist/assets/index-SvLVliAF.css` and
  `dist/assets/index-BrSS0O_p.js` in both.

One real failure occurred **during** the round and was fixed before handoff: the first
push (`f413d85`, CI run `42934118803`) failed the frontend **Build** step with
`vite.config.ts(2,19): error TS2307: Cannot find module '@vitejs/plugin-react' or its
corresponding type declarations` (exit code 2). Root cause: plugin-react v5 resolves
its types through the package `exports` map, which the tsconfigs' legacy
`moduleResolution: "Node"` cannot read; local builds had passed only because a stale
`tsconfig.node.tsbuildinfo` incremental cache let `tsc -b` skip rechecking
`vite.config.ts`. `b735b90` switched both tsconfigs to `moduleResolution: "bundler"`,
and everything was re-verified from a clean state (caches deleted, gates re-run, CI
green). That run is superseded by the green `42934586787` on the final code commit.

Known non-failures, for the record:

- Local pytest reports **1 warning** (starlette `BlockingPortal` alias), CI reports
  **2** — the extra one is passlib's `'crypt' is deprecated` DeprecationWarning,
  raised only on Linux, where the `crypt` module exists. Same asymmetry as round 1;
  both are third-party deprecation notices, not test failures.
- CI annotations are runner-environment notices, not job failures: the
  `Node.js 20 is deprecated … forced to run on Node.js 24` notes for
  `actions/checkout@v4`/`actions/setup-*@v4/v5`, and the `ubuntu-latest will migrate
  to Ubuntu 26` notice.
- Vite build warnings (chunk > 500 kB; lottie-web's internal direct `eval`) —
  pre-existing, non-fatal, unchanged in nature since round 1.
- Vitest's jsdom-environment performance note — informational output of the runner,
  not a failure.

## 9. Review points not implemented, with reasons

**None of the 14 findings was skipped or dropped.** All are implemented (section 3).
One execution-verification item could not be performed, for an environmental reason:

- **R-009's "run the stack once" half — Docker Compose has still never been executed
  on this machine.** Docker is not installed here, so `docker compose up --build`
  cannot be run. Everything the review required *in code* is done: the CORS origin is
  the browser origin (R-004), no JWT secret is committed (R-005), the frontend image
  is a production multi-stage build served by nginx on port 5173 with SPA-fallback
  `nginx.conf`, and the compose file passes `VITE_API_BASE_URL` as a build argument.
  These changes are statically verified (YAML/Dockerfile reviewed, the build commands
  the image runs are the exact ones that pass in CI) but **no container was ever
  built or run** — I am not claiming an execution I did not perform. The README
  documents the intended stack behaviour. This remains the one item that needs a
  machine with Docker to close out end to end.

No other deferrals. In particular, nothing was deferred under R-013: the audit count
is **0**, not a triaged subset — every vulnerability the review counted (18) is gone,
either by the toolchain upgrade or by the documented `minimatch` override, and the new
CI audit gate prevents silent regressions.
