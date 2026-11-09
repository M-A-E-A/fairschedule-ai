# FairSchedule AI project brief

## Problem

Universities and schools must coordinate academic demand, room scarcity, faculty workloads, and student availability while preserving fairness and transparency. Manual scheduling quickly becomes brittle when the institution grows or when disruptions appear.

## Proposed solution

FairSchedule AI brings together a tenant-aware scheduling API, a role-controlled web dashboard, and an optional AI layer that surfaces safe, evidence-based suggestions without bypassing the source of truth. The core scheduling engine uses OR-Tools CP-SAT to assign rooms and times under explicit constraints while leaving the final decision to authorized users.

## Scheduling model

- Hard constraints: room overlap, lecturer conflict, student-group conflict, capacity, room type, availability, and duration.
- Soft objectives: prefer earlier sessions, reduce large gaps, and preserve the original schedule where practical.
- Fairness objective: reduce clustering of undesirable slots across the population of student groups and faculty, while being transparent about the limits of optimization.

## Tenant isolation

Each institution is treated as a tenant. The backend validates the current user’s membership and role for every requested institution and campus before returning or mutating data. It rejects cross-tenant access even when an attacker can guess a resource ID.

## AI separation

The AI assistant is intentionally separated from the scheduling engine. It may answer filtered questions and propose a change, but it cannot issue direct updates. Any proposed change must be validated again by the backend before approval and audit logging.

## Evaluation metrics

- Number of hard-constraint violations
- Number of soft preference matches
- Number of undesirable time slots
- Time to generate a schedule
- Number of changes during repair
- Solver status (feasible, optimal, infeasible, or timeout)

This study uses deterministic demo inputs and reports solver results without claiming universal fairness or guaranteed performance beyond the local data set.
