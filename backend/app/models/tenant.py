from typing import Optional

from sqlmodel import Field, SQLModel


class Institution(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    slug: str
    tenant_code: str


class Campus(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id')
    name: str
    slug: str


class Department(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id')
    name: str


class Building(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    campus_id: int = Field(foreign_key='campus.id')
    name: str


class Room(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id')
    campus_id: int = Field(foreign_key='campus.id')
    name: str
    capacity: int
    room_type: str
    equipment: str = ''


class Lecturer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id')
    name: str
    email: str


class StudentGroup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id')
    name: str


class Course(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id')
    code: str
    name: str


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str
    password_hash: str = ''
    full_name: str
    role: str
    institution_id: int = Field(foreign_key='institution.id')


class SessionBooking(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id')
    campus_id: int = Field(foreign_key='campus.id')
    course_id: int = Field(foreign_key='course.id')
    lecturer_id: int = Field(foreign_key='lecturer.id')
    student_group_id: int = Field(foreign_key='studentgroup.id')
    room_id: int = Field(foreign_key='room.id')
    day: int
    start_minute: int
    duration_minute: int
    status: str = 'draft'


class ScheduleProposal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id')
    owner_email: str
    summary: str
    json_payload: str
    approved: bool = False


class AuditEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key='institution.id')
    user_email: str
    event_type: str
    message: str
