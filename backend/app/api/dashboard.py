"""Dashboard overview, campuses, and the role-scoped 'my schedule' view."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.deps import ensure_tenant, get_current_user
from app.core.db import get_session
from app.core.roles import STUDENT
from app.models import Campus, Course, Institution, Lecturer, Room, ScheduleProposal, SessionBooking, StudentGroup, User

router = APIRouter(tags=['dashboard'])

DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def format_minutes(value: int) -> str:
    return f'{value // 60:02d}:{value % 60:02d}'


def booking_to_dict(
    booking: SessionBooking,
    course: Course | None,
    lecturer: Lecturer | None,
    group: StudentGroup | None,
    room: Room | None,
) -> dict[str, Any]:
    return {
        'id': booking.id,
        'campus_id': booking.campus_id,
        'course_id': booking.course_id,
        'course_code': course.code if course else '',
        'course_name': course.name if course else '',
        'lecturer_id': booking.lecturer_id,
        'lecturer_name': lecturer.name if lecturer else '',
        'student_group_id': booking.student_group_id,
        'student_group_name': group.name if group else '',
        'room_id': booking.room_id,
        'room_name': room.name if room else '',
        'day': booking.day,
        'day_name': DAY_NAMES[booking.day] if 0 <= booking.day < len(DAY_NAMES) else str(booking.day),
        'start_minute': booking.start_minute,
        'start_time': format_minutes(booking.start_minute),
        'end_minute': booking.start_minute + booking.duration_minute,
        'end_time': format_minutes(booking.start_minute + booking.duration_minute),
        'duration_minute': booking.duration_minute,
        'status': booking.status,
    }


@router.get('/dashboard/overview')
def dashboard_overview(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> dict[str, Any]:
    institution_id = current_user.institution_id
    institution = session.get(Institution, institution_id)
    campuses = session.exec(select(Campus).where(Campus.institution_id == institution_id)).all()
    rooms = session.exec(select(Room).where(Room.institution_id == institution_id)).all()
    courses = session.exec(select(Course).where(Course.institution_id == institution_id)).all()
    lecturers = session.exec(select(Lecturer).where(Lecturer.institution_id == institution_id)).all()
    groups = session.exec(select(StudentGroup).where(StudentGroup.institution_id == institution_id)).all()
    bookings = session.exec(select(SessionBooking).where(SessionBooking.institution_id == institution_id)).all()
    proposals = session.exec(
        select(ScheduleProposal).where(
            ScheduleProposal.institution_id == institution_id,
            ScheduleProposal.approved == False,  # noqa: E712
        )
    ).all()
    return {
        'institution_id': institution_id,
        'institution_name': institution.name if institution else 'Unknown',
        'campuses': len(campuses),
        'rooms': len(rooms),
        'courses': len(courses),
        'lecturers': len(lecturers),
        'student_groups': len(groups),
        'sessions': len(bookings),
        'published_sessions': sum(1 for booking in bookings if booking.status == 'published'),
        'pending_proposals': len(proposals),
        'role': current_user.role,
    }


@router.get('/institutions/{institution_id}/campuses')
def list_campuses(
    institution_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    ensure_tenant(current_user, institution_id)
    rows = session.exec(select(Campus).where(Campus.institution_id == institution_id)).all()
    return [
        {
            'id': campus.id,
            'name': campus.name,
            'slug': campus.slug,
            'width': campus.width,
            'depth': campus.depth,
            'room_count': len(
                session.exec(select(Room).where(Room.campus_id == campus.id)).all(),
            ),
        }
        for campus in rows
    ]


@router.get('/institutions/{institution_id}/courses')
def list_courses(
    institution_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    ensure_tenant(current_user, institution_id)
    rows = session.exec(select(Course).where(Course.institution_id == institution_id)).all()
    return [
        {'id': row.id, 'code': row.code, 'name': row.name, 'required_room_type': row.required_room_type}
        for row in rows
    ]


@router.get('/institutions/{institution_id}/lecturers')
def list_lecturers(
    institution_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    ensure_tenant(current_user, institution_id)
    rows = session.exec(select(Lecturer).where(Lecturer.institution_id == institution_id)).all()
    return [{'id': row.id, 'name': row.name, 'email': row.email} for row in rows]


@router.get('/institutions/{institution_id}/student-groups')
def list_student_groups(
    institution_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    ensure_tenant(current_user, institution_id)
    rows = session.exec(select(StudentGroup).where(StudentGroup.institution_id == institution_id)).all()
    return [{'id': row.id, 'name': row.name, 'size': row.size} for row in rows]


@router.get('/me/schedule')
def my_schedule(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Each role sees its own sessions: students their cohort, faculty their
    teaching, campus operators and administrators the whole institution."""
    institution_id = current_user.institution_id
    bookings = session.exec(select(SessionBooking).where(SessionBooking.institution_id == institution_id)).all()
    if current_user.role == STUDENT:
        if current_user.student_group_id is None:
            return {'role': current_user.role, 'scope': 'student', 'sessions': []}
        bookings = [booking for booking in bookings if booking.student_group_id == current_user.student_group_id]
        scope = 'student'
    elif current_user.lecturer_id is not None:
        bookings = [booking for booking in bookings if booking.lecturer_id == current_user.lecturer_id]
        scope = 'lecturer'
    else:
        scope = 'institution'

    course_by_id = {row.id: row for row in session.exec(select(Course)).all()}
    lecturer_by_id = {row.id: row for row in session.exec(select(Lecturer)).all()}
    group_by_id = {row.id: row for row in session.exec(select(StudentGroup)).all()}
    room_by_id = {row.id: row for row in session.exec(select(Room)).all()}

    sessions = [
        booking_to_dict(
            booking,
            course_by_id.get(booking.course_id),
            lecturer_by_id.get(booking.lecturer_id),
            group_by_id.get(booking.student_group_id),
            room_by_id.get(booking.room_id),
        )
        for booking in bookings
    ]
    sessions.sort(key=lambda item: (item['day'], item['start_minute']))
    return {'role': current_user.role, 'scope': scope, 'sessions': sessions}


@router.get('/institutions/{institution_id}/timetable')
def institution_timetable(
    institution_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Full timetable visible to staff of the tenant (students get cohort-only
    data through /me/schedule instead, so this route is staff-only)."""
    ensure_tenant(current_user, institution_id)
    if current_user.role == STUDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='students use /me/schedule')
    bookings = session.exec(select(SessionBooking).where(SessionBooking.institution_id == institution_id)).all()
    course_by_id = {row.id: row for row in session.exec(select(Course)).all()}
    lecturer_by_id = {row.id: row for row in session.exec(select(Lecturer)).all()}
    group_by_id = {row.id: row for row in session.exec(select(StudentGroup)).all()}
    room_by_id = {row.id: row for row in session.exec(select(Room)).all()}
    sessions = [
        booking_to_dict(
            booking,
            course_by_id.get(booking.course_id),
            lecturer_by_id.get(booking.lecturer_id),
            group_by_id.get(booking.student_group_id),
            room_by_id.get(booking.room_id),
        )
        for booking in bookings
    ]
    sessions.sort(key=lambda item: (item['day'], item['start_minute']))
    return {'institution_id': institution_id, 'sessions': sessions}
