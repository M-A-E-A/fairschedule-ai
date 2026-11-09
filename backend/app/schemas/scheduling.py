from typing import Any, List

from pydantic import BaseModel


class SessionInput(BaseModel):
    course_id: int
    lecturer_id: int
    student_group_id: int
    room_id: int
    day: int
    start_minute: int
    duration_minute: int


class ScheduleRequest(BaseModel):
    institution_id: int
    campus_id: int
    days: List[int] = [0, 1, 2, 3, 4]
    start_minute: int = 480
    end_minute: int = 1080


class ScheduleProposalRequest(BaseModel):
    institution_id: int
    summary: str
    payload: dict[str, Any]
