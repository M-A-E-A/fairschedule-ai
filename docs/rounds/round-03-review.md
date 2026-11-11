# Round 3 review

- **Audited snapshot:** `a682bde` (handoff commit). The delta from the code snapshot
  `89c7547` is docs-only (`ISSUES.md` + `docs/rounds/round-03-handoff.md`), verified by
  `git diff 89c7547..a682bde`; the code under review is the tree at `89c7547`. The
  round-3 code delta from `b735b90` is exactly the three R-015 files
  (`backend/Dockerfile`, `backend/.dockerignore`, `backend/tests/test_docker_image.py`)
  plus docs — no file carrying any prior resolution was touched.
- **Scope:** all 110 tracked files read (full snapshot, not a diff), per the manifest in
  [`round-03-handoff.md`](round-03-handoff.md), which matches `git ls-files` exactly.
- **CI:** run `42937728527` (on `89c7547`, the code snapshot) cross-checked read-only via
  `gh run view --log` — it checks out `89c75471719fecd944e3c1908a09acb38145e14b` exactly
  (fetch ref and `git log -1` in the log) and matches the pasted log; run `42939141700`
  (on `a682bde`, the handoff commit) is also green. No failed runs since round 2's fix.

## Verdict

**APPROVE** — no blocking issues, no new findings, and all fifteen prior findings
verified resolved with none reintroduced. The single open item from the round-2 review
(R-015) was implemented exactly as specified and verified statically end to end. Per
`docs/AGENT_PROTOCOL.md`'s termination rule — zero open rows in the ledger index, no new
findings, all checks green — this verdict closes the loop.

## Blocking issues

**None.** All checks pass and local and CI agree:

- Backend: Ruff **All checks passed!**; pytest **115 passed** local and CI. Local shows
  1 warning vs CI's 2 — the extra CI warning is the Linux-only passlib `crypt`
  deprecation notice, disclosed since round 1 and verified in the raw CI log
  (`from crypt import crypt as _crypt`, passlib 1.7.4; Windows Python ships no `crypt`
  module). Tests pass in both environments, so this is an environmental notice, not a
  results disagreement.
- Frontend: ESLint clean; Vitest **12 files / 32 tests**; `npm audit` **0
  vulnerabilities**; `tsc -b && vite build` green with asset hashes
  `index-SvLVliAF.css` / `index-BrSS0O_p.js` identical local vs CI.
- The only red output anywhere in the round is the deliberate guard proof in handoff
  section 2, executed against the reverted pre-fix Dockerfile and restored immediately
  after (tree clean at the snapshot commit).

## Findings

**None.** Two borderline candidates were weighed and rejected as findings; both are
recorded so the judgment is auditable:

- *The regression guard does not evaluate `.dockerignore`.*
  `test_migrations_artifacts_exist_in_build_context` asserts the artifacts exist in the
  context directory and are COPY-referenced; it does not compute the post-`.dockerignore`
  effective context. Today that distinction is empty: every pattern in
  `backend/.dockerignore` was checked against Docker's documented matching semantics
  (patterns are anchored at the context root; `**` matches any number of directories
  including zero) and none can match `alembic.ini` or any tracked file under `alembic/`.
  The guard's scope is stated honestly in its own docstring, and the guard already
  exceeds what the round-2 fix demanded (the two `COPY` lines only — no test was
  required). Config files held correct by static review rather than automated guards is
  this loop's standing norm (`docker-compose.yml`, `frontend/nginx.conf` are handled the
  same way), so the unautomated link-4 of the handoff's evidence chain is a recorded
  boundary, not a defect.
- *No `docker build` step in CI.* Accepted — reasoning in the deferral judgment below.

## Deferral judgment — image never built or run; no CI `docker build` step

**Accepted, consistent with rounds 1 and 2.** Docker is not installed on this machine —
disclosed since round 1 and restated prominently in the handoff — so the backend image
was neither built nor run and the Compose stack was not executed. R-015's fix was
verified statically: handoff section 2's five-link evidence chain, each link
independently re-verified in this review.

1. `backend/app/main.py`'s lifespan calls `run_migrations()` unconditionally, and the
   image's only entrypoint is `uvicorn app.main:app`.
2. `BACKEND_ROOT = Path(__file__).resolve().parents[2]` resolves to `/app` in the image
   (`/app/app/core/migrations.py` → two parents up is `/app`), identical to the
   Dockerfile's `WORKDIR`; `build_alembic_config()` therefore reads `/app/alembic.ini`
   and `script_location` `/app/alembic`.
3. `COPY alembic.ini ./` and `COPY alembic ./alembic` place exactly those paths.
4. No `.dockerignore` pattern matches either artifact (verified against Docker's
   documented pattern semantics).
5. `docker-compose.yml`'s `./backend:/app` bind mount now shadows identical content
   instead of masking a broken image.

The declined CI `docker build` gate is accepted on the Developer's stated reasons, which
check out technically: a CI image build would **not** have caught R-015 — the pre-fix
image builds cleanly, because the failure manifests at container startup, not build
time — so the static guard covers the actual defect class (a `COPY` missing for a path
the startup code resolves) at least as precisely, and more directly. A CI-only step
that cannot be reproduced on this machine would also break the local/CI-symmetry
convention every round of this loop has enforced. The offer to add the gate on request
is noted; this review does not request it.

What remains is an environmental limitation, not an open issue: the first Docker-capable
machine should run `docker compose up --build` plus a standalone `docker run` boot check
(R-009's deferred execution half, now also exercising R-015's fix). The ledger records
this in the resolution text of R-009 and R-015.

## Prior-issue verification

No reintroductions found — the code delta since `b735b90` touches none of the files
carrying these resolutions, and each key invariant was re-checked in the current tree.
One line per issue:

- **R-001 — resolved:** `_revalidate_proposal` (stale-reference checks, post-application
  state reconstruction, `count_hard_violations` re-run, `409` + audited rejection) is
  present in `backend/app/api/scheduling.py`; its 5 regression tests are among the 115.
- **R-002 — resolved:** `email_verified` is surfaced by `exchange_code_for_identity` and
  enforced for both linking and provisioning, with a missing claim treated as unverified;
  tests in the 115.
- **R-003 — resolved:** `_validate_room_change` rejects capacity shrinks, room-type
  changes, and campus moves that would break a referencing booking; regression test in
  the 115.
- **R-004 — resolved in code:** `docker-compose.yml` sets
  `BACKEND_CORS_ORIGINS: http://localhost:5173`; execution remains the accepted
  environmental deferral.
- **R-005 — resolved:** no `JWT_SECRET` in any tracked file (the only Compose occurrence
  is the comment documenting its absence).
- **R-006 — resolved:** every Course/Lecturer/StudentGroup/Room lookup in dashboard,
  scheduling, and AI is institution-filtered at query level.
- **R-007 — resolved:** `/me/schedule` and the AI context branch on role first, with the
  explicit unlinked-faculty note.
- **R-008 — resolved:** `POST /ai/chat` takes the `AiChatRequest` schema with
  schema-driven 422s.
- **R-009 — resolved in code:** the frontend image remains the multi-stage production
  nginx build with `VITE_API_BASE_URL` as a build arg; execution half remains the
  accepted, disclosed environmental deferral.
- **R-010 — resolved:** no `USE_SQLITE_FOR_TESTS` in `.env.example`.
- **R-011 — resolved:** README documents `sqlite:///./demo.db` and the `harbor-admin`
  account; the login-page hint is pinned by a test.
- **R-012 — resolved:** `@react-three/drei` is absent from manifest and lockfile; no
  source imports exist.
- **R-013 — resolved:** `npm audit` reports 0 vulnerabilities with the gate wired into
  CI after `npm ci`; the documented `minimatch` override remains in place.
- **R-014 — resolved:** dummy-hash bcrypt equalization plus the sliding-window
  (IP, identifier) lockout with `429` + `Retry-After`; all 6 throttle tests in the 115.
- **R-015 — resolved (this round):** both specified `COPY` lines are present, placed
  after `COPY app` so the dependency layer stays cached; `.dockerignore` was tightened so
  the new layer cannot drag dev-machine caches into the image; the static guard pins the
  wiring and was proven to fail on the genuine pre-fix Dockerfile.

## Sound areas

- The R-015 fix is minimal, correctly placed, and self-documenting — the Dockerfile
  comment explains the boot dependency it exists to satisfy.
- The regression guard derives its needed paths from `build_alembic_config()` instead of
  hardcoded strings, and its `COPY` parser handles plain and JSON-list forms while
  skipping build flags.
- The `.dockerignore` rewrite matches Docker's documented pattern semantics precisely:
  root anchoring preserved, `**` forms cover nested caches, and no tracked alembic
  artifact can be excluded by any pattern.
- The handoff's evidence chain is honest: every claim is static and independently
  re-verifiable, and the one deliberately red run (the guard proof against the pre-fix
  Dockerfile) is labeled as such rather than hidden.
- The standing areas audited sound in round 2 are unchanged by this delta: the pure
  OR-Tools scheduler, query-level tenant isolation, server-side RBAC, the revalidated
  proposal lifecycle, throttled and timing-equalized auth, and the typed, accessible
  frontend layer.
