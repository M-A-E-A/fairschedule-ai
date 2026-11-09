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

## Round log

### Baseline (pre-loop)

Starting state handed to the Developer before round 1: a partial scaffold containing a
FastAPI backend with 6 tests, a React/Vite frontend with 1 test, a GitHub Actions
workflow, `docker-compose.yml`, and this ledger. Known gaps at baseline included no lint
tooling anywhere, no Alembic migrations, no backend role enforcement, an unauthenticated
tenant-leaking endpoint, a stubbed SSO path, and no `frontend/Dockerfile` despite
`docker-compose.yml` declaring `build: ./frontend`.

### Round 1

- **Developer:** pending.
- **Reviewer:** pending.
