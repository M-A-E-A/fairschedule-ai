"""Tenant-aware SQLModel tables.

Every institution is a tenant. All business tables carry ``institution_id``
so that tenant isolation can be enforced in every query.
"""

from __future__ import annotations

from typing import Optional

from sqlmodel import Field, SQLModel


class Institution(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(index=True, unique=True)
    tenant_code: str


class Campus(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    name: str
    slug: str
    # Rough footprint used by the 3D campus view (metres).
    width: float = 40.0
    depth: float = 30.0


class Department(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    name: str


class Building(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    campus_id: int = Field(foreign_key='campus.id', index=True)
    name: str


class Room(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    campus_id: int = Field(foreign_key='campus.id', index=True)
    name: str
    capacity: int
    room_type: str = 'lecture'
    equipment: str = ''


class Lecturer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    name: str
    email: str


class StudentGroup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    name: str
    # Head count; the solver refuses rooms that cannot seat the group.
    size: int = 30


class Course(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    code: str
    name: str
    # Room type the course requires ('any' accepts every room).
    required_room_type: str = 'any'


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # App-managed username used for password sign-in; unique per deployment.
    username: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    password_hash: str = ''
    full_name: str
    role: str
    institution_id: int = Field(foreign_key='institution.id', index=True)
    is_active: bool = True
    # Set when the account was linked to an external identity provider.
    external_subject: Optional[str] = Field(default=None, index=True)
    external_provider: str = ''
    # Role-specific links used for "my schedule" views.
    student_group_id: Optional[int] = Field(default=None, foreign_key='studentgroup.id')
    lecturer_id: Optional[int] = Field(default=None, foreign_key='lecturer.id')


class SessionBooking(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
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
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    campus_id: int = Field(foreign_key='campus.id', default=0)
    owner_email: str
    summary: str
    json_payload: str
    approved: bool = False


class AuditEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id', index=True)
    user_email: str
    event_type: str
    message: str
