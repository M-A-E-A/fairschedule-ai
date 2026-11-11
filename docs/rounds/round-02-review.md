# Round 2 review

- **Audited snapshot:** `e911fa0` (handoff commit). The delta from the code snapshot
  `b735b90` is docs-only (`ISSUES.md` + this round's handoff), verified by
  `git diff b735b90..e911fa0`; the code under review is the tree at `b735b90`.
- **Scope:** all 107 tracked files read (full snapshot, not a diff), per the manifest in
  [`round-02-handoff.md`](round-02-handoff.md), which matches `git ls-files` exactly.
- **CI:** run `42934586787` cross-checked read-only via `gh run view --log`; it checks out
  `b735b9018ed9218e646ac4d1ff295535523bbe8b` exactly and matches the pasted log. The
  interim failed run `42934118803` was on `f413d85` (pre-fix) and is superseded by the
  green run on `b735b90`.

## Verdict

**REJECT** — no blocking issues, all 14 prior findings verified resolved in code, and
**one new finding (R-015)**: the backend Docker image cannot boot outside Compose because
`alembic.ini` and the `alembic/` migration chain are never copied into it. The fix is
static (two `COPY` lines) and does not require Docker on this machine.

## Blocking issues

**None.** All checks pass and local and CI agree:

- Backend: Ruff **All checks passed!**; pytest **113 passed** (local shows 1 warning vs
  CI's 2 — the extra CI warning is the Linux-only passlib `crypt` deprecation notice,
  disclosed in the handoff; a third-party notice, not a code defect; tests pass in both
  environments).
- Frontend: ESLint clean; Vitest **12 files / 32 tests**; `npm audit` **0
  vulnerabilities**; `tsc -b && vite build` green with asset hashes
  `index-SvLVliAF.css` / `index-BrSS0O_p.js` identical local vs CI.

## Findings

### R-015 — Backend image is unbootable outside Compose: `alembic.ini` and `alembic/` are not copied into it

- **Location:** `backend/Dockerfile` (lines 3–5 — only `requirements.txt` and `app/` are
  copied), against `backend/app/core/migrations.py` (`BACKEND_ROOT` resolves to `/app`
  in the image; `build_alembic_config()` reads `BACKEND_ROOT / 'alembic.ini'` and sets
  `script_location` to `BACKEND_ROOT / 'alembic'`), `backend/app/main.py` (lifespan
  calls `run_migrations()` unconditionally at startup), and `docker-compose.yml`
  (backend `volumes: ./backend:/app`).
- **Problem:** The image omits `alembic.ini` and the `alembic/` migration chain, but the
  container's only entrypoint (`uvicorn app.main:app`) runs Alembic at startup through
  the lifespan. Both artifacts are tracked and not excluded by `backend/.dockerignore` —
  they are in the build context and simply never copied.
- **Consequence:** Any standalone use of the built image (`docker build backend/` then
  `docker run`) fails during startup when Alembic cannot find its script directory, so
  the "shipped" backend image is broken outside one specific orchestration file. The
  documented stack only works because Compose bind-mounts `./backend:/app` over the
  image — which also means the image's `COPY app ./app` layer is dead weight under
  Compose, and anyone who productionizes the Compose file by dropping the dev bind mount
  gets a container that cannot boot. CI never builds the image, so nothing catches this.
  This is precisely the class of wiring bug R-009's run-the-stack requirement exists to
  catch, and it went unnoticed because the stack has never been executed.
- **Fix:** Add to `backend/Dockerfile`:

  ```dockerfile
  COPY alembic.ini ./
  COPY alembic ./alembic
  ```

  The image is then self-contained and the Compose bind mount becomes a genuine dev
  convenience instead of a load-bearing mask. This fix is verifiable statically (both
  paths exist in the build context and are referenced by `app.core.migrations`); it does
  not require Docker on this machine. When a Docker-capable machine is available, the
  still-deferred `docker compose up --build` (R-009) will close the loop end to end.

## Deferral judgment — R-009's execution half

**Accepted as a justified deferral.** The round-1 fix itself conditioned the execution on
"once Docker is available"; Docker is not installed on this machine (a fact disclosed
since round 1), and the handoff's section 9 states exactly why, prominently, without
claiming an execution that did not happen — which is what the protocol requires ("states
exactly why instead of silently skipping it"). Everything R-004/R-005/R-009 required *in
code* is verified genuinely present and correct: the CORS origin is the browser origin,
no secret is committed, and the frontend image is a real multi-stage production build.

The deferral is accepted, not forgotten: it remains an open environmental item to be
closed at the first opportunity on a Docker-capable machine — and R-015 above is concrete
evidence that the risk R-009 flagged was real, not hypothetical.

## Prior-issue verification

No reintroductions found. One line per issue:

- **R-001 — resolved:** `approve_proposal` → `_revalidate_proposal` checks stale
  references (session deleted/moved campus; room deleted/moved off campus), reconstructs
  the full post-application state, re-runs `count_hard_violations`, and rejects `409`
  with an audited `proposal_rejected`; 5 regression tests pin the behavior. The
  institution-wide reconstruction cannot spuriously reject valid proposals because
  write-time conflict checks in `bookings.py` are institution-wide too.
- **R-002 — resolved:** `exchange_code_for_identity` surfaces `email_verified` and it is
  enforced for both linking (any role, including administrators) and provisioning; a
  missing claim is treated as unverified; subject-matched links bypass the check; 4+
  tests.
- **R-003 — resolved:** `_validate_room_change` rejects capacity shrinks, room-type
  changes, and campus moves that would break a referencing booking, with the documented
  reject policy and a thorough regression test.
- **R-004 — resolved in code:** Compose sets `BACKEND_CORS_ORIGINS: http://localhost:5173`
  — the browser origin (execution still deferred; see above).
- **R-005 — resolved:** no `JWT_SECRET` anywhere in tracked files; `APP_ENV=development`
  generates the ephemeral per-process secret.
- **R-006 — resolved:** every Course/Lecturer/StudentGroup/Room lookup in dashboard,
  scheduling, and AI is institution-filtered at query level.
- **R-007 — resolved:** `/me/schedule` and AI context branch on role first; the dead
  `_faculty_context` branch is gone.
- **R-008 — resolved:** `POST /ai/chat` takes the `AiChatRequest` schema (1–2000 chars,
  blank rejected) with schema-driven 422s.
- **R-009 — resolved in code:** frontend image is a true multi-stage production build
  (`node:20-alpine` `npm ci` + `npm run build` → `nginx:1.27-alpine` on 5173 with SPA
  fallback), `VITE_API_BASE_URL` wired as a build arg; execution half is a justified,
  tracked deferral.
- **R-010 — resolved:** `USE_SQLITE_FOR_TESTS` deleted from `.env.example`.
- **R-011 — resolved:** README documents `sqlite:///./demo.db` and
  `harbor-admin` / `demo-admin-harbor`; the login-page hint matches and is pinned by a
  test.
- **R-012 — resolved:** `@react-three/drei` and `three-mesh-bvh` are gone from manifest
  and lockfile; no source imports exist.
- **R-013 — resolved:** audit reports **0** vulnerabilities with a CI gate
  (`npm audit --audit-level=high`) after `npm ci`; the lockfile carries a single
  `minimatch` 11.0.7 entry, confirming the documented, load-bearing `^11.0.5` override;
  the major-version migrations (router 7, vite 8, vitest 5, plugin-react 5) left no dead
  code, no v6 router API usage, no config drift — both tsconfigs use
  `moduleResolution: "bundler"` + `module: ESNext`, and the build is green.
- **R-014 — resolved:** every 401 pays exactly one bcrypt verification (dummy hash when
  no user), sliding-window lockout of 5 failures / 15 min keyed on (IP, identifier),
  identical for unknown accounts, success resets; 6 tests.

## Sound areas

- The OR-Tools scheduler is clean and pure: constraints, metrics, greedy fallback, and
  repair never mutate input sessions (pinned by test).
- Tenant isolation is enforced at query level consistently across every endpoint, not
  filtered after the fact.
- The RBAC matrix is enforced server-side and mirrored (never replaced) by the UI
  guards and role-filtered navigation.
- The proposal lifecycle (generate → pending proposal → revalidated approve → publish
  with audit trail) is coherent and idempotent-rejecting.
- Auth is solid: username+email login, JWT handling, SSO link/provision behind the
  email-verification gate, and login throttling with constant-time 401s.
- The frontend is a typed API layer end to end with accessible forms (labels, roles,
  `status`/`alert` semantics) and integration-grade tests exercising real route
  mounting.
- Dependency and config hygiene: fully pinned requirements with the documented
  `bcrypt==4.0.1` pin, documented Ruff exemptions, and Alembic sharing the app's
  settings as the single source of truth for the database URL.
