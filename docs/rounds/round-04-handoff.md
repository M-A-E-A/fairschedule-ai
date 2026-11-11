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
| S-01 | Solver time limit | done | (this commit) |
| S-02 | Rate-limiter persistence | pending | — |
| S-03 | PostgreSQL exercised in CI | pending | — |
| S-04 | Docker build + container smoke test in CI | pending | — |
| S-05 | 3D campus ↔ schedule integration | pending | — |
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

## Interim failures

(Each push's CI failures, root causes, and fixes are recorded here as they
happen.)
