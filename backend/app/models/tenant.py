"""Tenant-aware SQLModel tables.

Every institution is a tenant. All business tables carry ``institution_id``
so that tenant isolation can be enforced in every query.

``LoginAttempt`` is the one auth-infrastructure table without a tenant
column: it records password-login *failures* keyed by the identifier the
client attempted, which exists before authentication resolves a tenant.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class Institution(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(index=True, unique=True)
    tenant_code: str


class Campus(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    name: str
    slug: str
    # Rough footprint used by the 3D campus view (metres).
    width: float = 40.0
    depth: float = 30.0


class Department(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    name: str


class Building(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    campus_id: int = Field(foreign_key='campus.id', index=True)
    name: str


class Room(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    campus_id: int = Field(foreign_key='campus.id', index=True)
    name: str
    capacity: int
    room_type: str = 'lecture'
    equipment: str = ''


class Lecturer(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    name: str
    email: str


class StudentGroup(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    name: str
    # Head count; the solver refuses rooms that cannot seat the group.
    size: int = 30


class Course(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    code: str
    name: str
    # Room type the course requires ('any' accepts every room).
    required_room_type: str = 'any'


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    # App-managed username used for password sign-in; unique per deployment.
    username: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    password_hash: str = ''
    full_name: str
    role: str
    institution_id: int = Field(foreign_key='institution.id', index=True)
    is_active: bool = True
    # Set when the account was linked to an external identity provider.
    external_subject: str | None = Field(default=None, index=True)
    external_provider: str = ''
    # Role-specific links used for "my schedule" views.
    student_group_id: int | None = Field(default=None, foreign_key='studentgroup.id')
    lecturer_id: int | None = Field(default=None, foreign_key='lecturer.id')


class SessionBooking(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    campus_id: int = Field(foreign_key='campus.id', index=True)
    course_id: int = Field(foreign_key='course.id', index=True)
    lecturer_id: int = Field(foreign_key='lecturer.id', index=True)
    student_group_id: int = Field(foreign_key='studentgroup.id', index=True)
    room_id: int = Field(foreign_key='room.id', index=True)
    day: int
    start_minute: int
    duration_minute: int
    status: str = 'draft'


class ScheduleProposal(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    campus_id: int = Field(foreign_key='campus.id', default=0)
    owner_email: str
    summary: str
    json_payload: str
    approved: bool = False


class AuditEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    user_email: str
    event_type: str
    message: str


class TimetableVersion(SQLModel, table=True):
    """A named, frozen snapshot of a tenant's published timetable (S-06).

    Publishing copies the institution's current booking rows into
    ``json_payload``; later draft edits never rewrite a stored version, so any
    published version stays queryable exactly as it was published (the diff
    endpoint compares the live draft against the latest one). ``version`` is
    a per-tenant 1-based sequence assigned at publish time, unique per
    institution.
    """

    id: int | None = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    version: int
    label: str
    published_by_email: str
    published_at: datetime
    json_payload: str

    __table_args__ = (
        Index('uq_timetableversion_inst_version', 'institution_id', 'version', unique=True),
    )


class LoginAttempt(SQLModel, table=True):
    """One failed password-login attempt (S-02: brute-force throttling store).

    Rows live in the application database so every worker and replica of a
    deployment counts the same sliding window, and a fresh process inherits
    the failures recorded before it started. ``client_ip`` plus ``identifier``
    (the username *or* email the client attempted, lower-cased by the
    caller) is the throttle key; ``identifier`` deliberately needs to resolve
    to no account — unknown and known accounts must throttle identically.
    ``failed_at`` is wall-clock UTC because the window must survive process
    restarts (a monotonic clock would reset with each process).
    """

    id: int | None = Field(default=None, primary_key=True)
    client_ip: str
    identifier: str
    failed_at: datetime

    __table_args__ = (
        Index('ix_loginattempt_key', 'client_ip', 'identifier'),
        Index('ix_loginattempt_failed_at', 'failed_at'),
    )
