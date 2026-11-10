"""Role definitions and the role matrix used for backend access control."""

from __future__ import annotations

ADMINISTRATOR = 'administrator'
CAMPUS_OPERATOR = 'campus_operator'
FACULTY = 'faculty'
STUDENT = 'student'

ALL_ROLES: tuple[str, ...] = (ADMINISTRATOR, CAMPUS_OPERATOR, FACULTY, STUDENT)

# Roles that plan, allocate rooms, and run the solver.
SCHEDULE_MANAGERS: tuple[str, ...] = (ADMINISTRATOR, CAMPUS_OPERATOR, FACULTY)
# Roles that may approve and publish a generated proposal.
PROPOSAL_APPROVERS: tuple[str, ...] = (ADMINISTRATOR, CAMPUS_OPERATOR)
# Roles that may mutate rooms and bookings.
RESOURCE_MANAGERS: tuple[str, ...] = (ADMINISTRATOR, CAMPUS_OPERATOR, FACULTY)
# Roles that may manage rooms only (room allocation is an operator duty).
ROOM_MANAGERS: tuple[str, ...] = (ADMINISTRATOR, CAMPUS_OPERATOR)
