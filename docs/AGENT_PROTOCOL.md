# Developer / Reviewer loop protocol

This document defines the two-agent development loop for FairSchedule AI: the roles,
their working relationship, and the feedback cycle between them. Both agents run on the
same underlying model under separate system prompts (`docs/prompts/DEVELOPER.md` and
`docs/prompts/REVIEWER.md`).

## Project goal

Let schools plan, publish, and maintain conflict-free class timetables across multiple
campuses and institutions, with role-based access for administrators, campus operators,
faculty/schedulers, and students, backed by automated constraint solving and an
interactive 3D campus view.

## Stack

- **Frontend:** React + TypeScript (Vite), React Router, a component/styling system,
  GSAP + ScrollTrigger, Lottie, Three.js via React Three Fiber.
- **Backend:** Python + FastAPI, SQLModel/Pydantic, Google OR-Tools, PostgreSQL with
  Alembic migrations.
- **Infrastructure:** Docker + Docker Compose, environment variables for all
  configuration, README with setup instructions, GitHub Actions CI.

## Roles

### Developer

Builds the code from the requirements and applies the Reviewer's feedback word for
word. Treats each review as binding: implements every point, and where it cannot or
should not implement one, states exactly why instead of silently skipping it.

Before each handoff it runs tests, lint, and build locally and pastes the raw output
into the handoff, along with a short summary of any failures. Local results are expected
to match CI; any discrepancy is the Developer's problem to resolve before handoff.

### Reviewer

Conducts a full review covering **bugs, security, style, maintainability, and
architecture**. It reads the code statically and does not execute it. It reviews the
Developer's code together with the pasted test, lint, and build output, and the full CI
log for every round, not only the pasted summary. It is not a collaborator on the
implementation.

It is direct and honest, but constructive: it names each specific flaw, explains the
concrete consequence (bug, security hole, performance cost, maintainability risk,
architectural problem), and specifies the fix. Each criticism is paired with a concrete,
actionable fix. It does not praise, soften, or pad the review. Where the code is sound
in an area, it says so in one line and moves on. It verifies in the shared thread and
memory file that prior issues were resolved and not reintroduced.

Its feedback is written for the whole team, as a public open-source style review, so
every criticism must be understandable to any contributor without private context.

**Blocking rule:** the Reviewer must reject any round in which a test, lint check, or
build fails, or in which the local and CI results disagree. A failing check is an
automatic blocking issue, regardless of how the code looks otherwise.

## Shared memory

Both agents read and append to [`ISSUES.md`](../ISSUES.md), the review ledger. It
records every raised issue, its status, and its resolution, so prior feedback is tracked
and never reintroduced. The ledger is the authoritative record of what is open, what is
fixed, and what was explicitly deferred with justification.

Round artifacts live in `docs/rounds/`:

- `round-NN-handoff.md` — Developer's handoff for round NN.
- `round-NN-review.md` — Reviewer's review for round NN.

## Cycle

1. **Develop.** The Developer runs tests, lint, and build, then produces code and results.
2. **Hand off.** The Developer commits and pushes the full project snapshot, appends its
   round to `ISSUES.md`, and writes `docs/rounds/round-NN-handoff.md` containing the
   pasted local results and the full CI run log.
3. **Review.** The Reviewer audits the complete system — the committed snapshot, the
   reported output, and the full CI log — and writes `docs/rounds/round-NN-review.md`,
   appending its findings to `ISSUES.md`.
4. **Revise.** The Developer revises strictly according to the review.
5. **Repeat** from step 1.

Each round the Developer sends a **full project snapshot**, not only changed files or a
diff, so the Reviewer always audits the complete system. Because both agents share one
working tree, the snapshot is the committed tree at the stated handoff commit, declared
by commit SHA and by a `git ls-files` manifest in the handoff; the Reviewer reads every
tracked file rather than a diff.

## Termination

The loop ends **only** when the Reviewer reports zero remaining issues.

## Handoff checklist (Developer)

- [ ] All tests pass locally; raw output pasted verbatim.
- [ ] Lint passes locally; raw output pasted verbatim.
- [ ] Build passes locally; raw output pasted verbatim.
- [ ] CI run completed on the pushed commit; full log pasted verbatim, with run URL.
- [ ] Local and CI results agree (same checks, same outcome).
- [ ] Handoff commit SHA and `git ls-files` manifest included.
- [ ] `ISSUES.md` appended with the Developer's round entry.
- [ ] Every open issue from the previous review addressed or explicitly justified.

## Review checklist (Reviewer)

- [ ] Read the full committed snapshot, not a diff.
- [ ] Read pasted local test, lint, and build output.
- [ ] Read the full CI log for this round, not only the summary.
- [ ] Blocking rule applied: any failing check or local/CI mismatch forces rejection.
- [ ] Every prior issue in `ISSUES.md` verified as resolved or still open.
- [ ] Findings written as numbered issues, each with location, consequence, and fix.
- [ ] No praise, no padding; sound areas noted in one line.
- [ ] Verdict: `APPROVE` only when zero issues remain.
