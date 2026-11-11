"""Schemas for scheduling, room, and booking endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScheduleGenerateRequest(BaseModel):
    institution_id: int
    campus_id: int
    days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    day_start: int = 480
    day_end: int = 1080
    allow_time_change: bool = True
    # Explicit per-request override of the SOLVER_TIME_LIMIT_SECONDS default;
    # when omitted the endpoint uses the environment-configured default.
    time_limit_seconds: float | None = Field(default=None, ge=0.5, le=3600.0)


class RoomCreateRequest(BaseModel):
    campus_id: int
    name: str = Field(min_length=1, max_length=64)
    capacity: int = Field(ge=1, le=10000)
    room_type: str = Field(default='lecture', min_length=1, max_length=32)
    equipment: str = ''


class RoomUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    capacity: int | None = Field(default=None, ge=1, le=10000)
    room_type: str | None = Field(default=None, min_length=1, max_length=32)
    equipment: str | None = None
    campus_id: int | None = None


class BookingCreateRequest(BaseModel):
    campus_id: int
    course_id: int
    lecturer_id: int
    student_group_id: int
    room_id: int
    day: int = Field(ge=0, le=6)
    start_minute: int = Field(ge=0, le=1439)
    duration_minute: int = Field(ge=15, le=480)
    status: str = 'draft'


class BookingUpdateRequest(BaseModel):
    campus_id: int | None = None
    course_id: int | None = None
    lecturer_id: int | None = None
    student_group_id: int | None = None
    room_id: int | None = None
    day: int | None = Field(default=None, ge=0, le=6)
    start_minute: int | None = Field(default=None, ge=0, le=1439)
    duration_minute: int | None = Field(default=None, ge=15, le=480)
    status: str | None = None


class TimetablePublishRequest(BaseModel):
    # Human name for the published version; blank falls back to "Version N".
    label: str = Field(default='', max_length=120)


class ScheduleProposalRequest(BaseModel):
    institution_id: int
    summary: str
    payload: dict[str, Any]
