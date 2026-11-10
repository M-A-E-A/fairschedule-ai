"""AI assistant endpoint.

Deliberately separated from the scheduling engine (docs/PROJECT.md): it only
*reads* role- and tenant-filtered data and answers questions. It can never
issue direct updates — any change must travel through a schedule proposal that
an authorised user approves.

When no external AI provider is configured, it answers deterministically from
the authorized dataset, so the endpoint stays useful and testable offline.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_session
from app.core.roles import STUDENT
from app.models import Course, Institution, Lecturer, Room, ScheduleProposal, SessionBooking, StudentGroup, User

router = APIRouter(tags=['ai'])
settings = get_settings()

DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _format_time(minute: int) -> str:
    return f'{minute // 60:02d}:{minute % 60:02d}'


def _student_context(user: User, session: Session) -> str:
    if user.student_group_id is None:
        return 'You are not linked to a student group, so there are no sessions to show for your account.'
    bookings = session.exec(
        select(SessionBooking).where(
            SessionBooking.institution_id == user.institution_id,
            SessionBooking.student_group_id == user.student_group_id,
        )
    ).all()
    if not bookings:
        return 'Your cohort has no scheduled sessions yet.'
    course_by_id = {row.id: row for row in session.exec(select(Course)).all()}
    room_by_id = {row.id: row for row in session.exec(select(Room)).all()}
    group = session.get(StudentGroup, user.student_group_id)
    lines = [f'Your cohort ({group.name if group else "your group"}) has {len(bookings)} session(s):']
    for booking in sorted(bookings, key=lambda item: (item.day, item.start_minute)):
        course = course_by_id.get(booking.course_id)
        room = room_by_id.get(booking.room_id)
        label = f'{course.code} {course.name}' if course else 'Session'
        lines.append(
            f'- {DAY_NAMES[booking.day] if 0 <= booking.day < len(DAY_NAMES) else booking.day} '
            f'{_format_time(booking.start_minute)}-{_format_time(booking.start_minute + booking.duration_minute)} '
            f'{label} in {room.name if room else "TBD"}'
        )
    return '\n'.join(lines)


def _faculty_context(user: User, session: Session) -> str:
    if user.lecturer_id is None:
        return 'Your account is not linked to a lecturer record, so no teaching sessions are attached to it.'
    bookings = session.exec(
        select(SessionBooking).where(
            SessionBooking.institution_id == user.institution_id,
            SessionBooking.lecturer_id == user.lecturer_id,
        )
    ).all()
    if not bookings:
        return 'You have no scheduled teaching sessions.'
    course_by_id = {row.id: row for row in session.exec(select(Course)).all()}
    lines = [f'You teach {len(bookings)} scheduled session(s):']
    for booking in sorted(bookings, key=lambda item: (item.day, item.start_minute)):
        course = course_by_id.get(booking.course_id)
        label = f'{course.code} {course.name}' if course else 'Session'
        lines.append(
            f'- {DAY_NAMES[booking.day] if 0 <= booking.day < len(DAY_NAMES) else booking.day} '
            f'{_format_time(booking.start_minute)}-{_format_time(booking.start_minute + booking.duration_minute)} '
            f'{label}'
        )
    return '\n'.join(lines)


def _staff_context(user: User, session: Session) -> str:
    institution = session.get(Institution, user.institution_id)
    rooms = session.exec(select(Room).where(Room.institution_id == user.institution_id)).all()
    courses = session.exec(select(Course).where(Course.institution_id == user.institution_id)).all()
    lecturers = session.exec(select(Lecturer).where(Lecturer.institution_id == user.institution_id)).all()
    bookings = session.exec(select(SessionBooking).where(SessionBooking.institution_id == user.institution_id)).all()
    proposals = session.exec(
        select(ScheduleProposal).where(
            ScheduleProposal.institution_id == user.institution_id, ScheduleProposal.approved == False  # noqa: E712
        )
    ).all()
    total_seats = sum(room.capacity for room in rooms)
    return (
        f'{institution.name if institution else "Your institution"} overview: '
        f'{len(rooms)} room(s) ({total_seats} seats), {len(courses)} course(s), '
        f'{len(lecturers)} lecturer(s), {len(bookings)} scheduled session(s), '
        f'{len(proposals)} pending proposal(s).'
    )


@router.post('/ai/chat')
def ai_chat(
    payload: dict[str, Any],
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    prompt = (payload.get('prompt') or '').strip()
    if not prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='prompt required')

    if current_user.role == STUDENT:
        context = _student_context(current_user, session)
    elif current_user.lecturer_id is not None:
        context = _faculty_context(current_user, session)
    else:
        context = _staff_context(current_user, session)

    provider_note = (
        'AI is not configured for this deployment; this answer comes only from '
        'schedule data you are authorized to see.'
        if settings.ai_provider == 'none'
        else 'Answer grounded in your authorized schedule data.'
    )
    answer = (
        f'{provider_note}\n\n'
        f'Question: {prompt}\n\n{context}\n\n'
        'I cannot change schedules directly. To alter the timetable, generate a '
        'schedule proposal and have an administrator or campus operator approve it.'
    )
    return {'answer': answer, 'scope': current_user.role}
