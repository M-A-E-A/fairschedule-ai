"""Booking (session) CRUD with write-time enforcement of the hard constraints.

Every mutation revalidates room overlap, lecturer conflicts, student-group
conflicts, capacity, and room type against the tenant's existing bookings, so
a violating schedule can never reach the database even if the solver is
bypassed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from app.api.deps import ensure_tenant, get_current_user, require_roles
from app.core.db import get_session
from app.core.roles import RESOURCE_MANAGERS, STUDENT
from app.models import Campus, Course, Lecturer, Room, SessionBooking, StudentGroup, User
from app.schemas.scheduling import BookingCreateRequest, BookingUpdateRequest
from app.services.scheduler import find_booking_conflicts

router = APIRouter(tags=['bookings'])

# Human-readable words for the conflict kinds returned by
# ``find_booking_conflicts`` so error details stay readable.
_CONFLICT_LABELS = {
    'room_conflict': 'room',
    'lecturer_conflict': 'lecturer',
    'group_conflict': 'student_group',
}


def _tenant_resource(session: Session, model, resource_id: int, institution_id: int, label: str):
    resource = session.get(model, resource_id)
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'{label} not found')
    if resource.institution_id != institution_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f'{label} belongs to another institution')
    return resource


def _validate_hard_constraints(
    session: Session,
    institution_id: int,
    candidate: dict[str, Any],
) -> None:
    """Reject bookings that violate capacity, room type, or overlap rules."""
    room = session.get(Room, candidate['room_id'])
    group = session.get(StudentGroup, candidate['student_group_id'])
    course = session.get(Course, candidate['course_id'])
    if room is not None and group is not None and room.capacity < group.size:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'capacity violated: {room.name} seats {room.capacity}, group needs {group.size}',
        )
    if room is not None and course is not None:
        required = course.required_room_type
        if required not in ('any', '', None) and room.room_type != required:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'room type violated: {course.code} requires {required}, {room.name} is {room.room_type}',
            )
    existing = session.exec(select(SessionBooking).where(SessionBooking.institution_id == institution_id)).all()
    existing_dicts = [
        {
            'id': booking.id,
            'day': booking.day,
            'start_minute': booking.start_minute,
            'duration_minute': booking.duration_minute,
            'room_id': booking.room_id,
            'lecturer_id': booking.lecturer_id,
            'student_group_id': booking.student_group_id,
        }
        for booking in existing
    ]
    conflicts = find_booking_conflicts(candidate, existing_dicts)
    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='conflicting ' + ', '.join(_CONFLICT_LABELS[kind] for kind in conflicts)
            + ' booking at that time',
        )


def _booking_dict(booking: SessionBooking) -> dict[str, Any]:
    return {
        'id': booking.id,
        'institution_id': booking.institution_id,
        'campus_id': booking.campus_id,
        'course_id': booking.course_id,
        'lecturer_id': booking.lecturer_id,
        'student_group_id': booking.student_group_id,
        'room_id': booking.room_id,
        'day': booking.day,
        'start_minute': booking.start_minute,
        'duration_minute': booking.duration_minute,
        'status': booking.status,
    }


def _get_booking(session: Session, booking_id: int, user: User) -> SessionBooking:
    booking = session.get(SessionBooking, booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='booking not found')
    ensure_tenant(user, booking.institution_id)
    return booking


@router.get('/institutions/{institution_id}/bookings')
def list_bookings(
    institution_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    ensure_tenant(current_user, institution_id)
    rows = session.exec(select(SessionBooking).where(SessionBooking.institution_id == institution_id)).all()
    if current_user.role == STUDENT:
        # Students only ever see their own cohort's sessions here.
        rows = [row for row in rows if row.student_group_id == current_user.student_group_id]
    return [_booking_dict(row) for row in rows]


@router.post('/institutions/{institution_id}/bookings', status_code=status.HTTP_201_CREATED)
def create_booking(
    institution_id: int,
    payload: BookingCreateRequest,
    current_user: User = Depends(require_roles(*RESOURCE_MANAGERS)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    ensure_tenant(current_user, institution_id)
    _tenant_resource(session, Course, payload.course_id, institution_id, 'course')
    _tenant_resource(session, Lecturer, payload.lecturer_id, institution_id, 'lecturer')
    _tenant_resource(session, StudentGroup, payload.student_group_id, institution_id, 'student group')
    room = _tenant_resource(session, Room, payload.room_id, institution_id, 'room')
    campus_id = payload.campus_id
    if room.campus_id != campus_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='room is not on that campus')
    candidate = payload.model_dump()
    candidate['id'] = None
    _validate_hard_constraints(session, institution_id, candidate)
    booking = SessionBooking(institution_id=institution_id, **candidate)
    session.add(booking)
    session.commit()
    session.refresh(booking)
    return _booking_dict(booking)


@router.patch('/bookings/{booking_id}')
def update_booking(
    booking_id: int,
    payload: BookingUpdateRequest,
    current_user: User = Depends(require_roles(*RESOURCE_MANAGERS)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    booking = _get_booking(session, booking_id, current_user)
    changes = payload.model_dump(exclude_unset=True)
    changes = {field: value for field, value in changes.items() if value is not None}
    merged = _booking_dict(booking) | changes
    if 'room_id' in changes:
        room = _tenant_resource(session, Room, changes['room_id'], booking.institution_id, 'room')
        if room.campus_id != merged['campus_id']:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='room is not on that campus')
    if 'course_id' in changes:
        _tenant_resource(session, Course, changes['course_id'], booking.institution_id, 'course')
    if 'lecturer_id' in changes:
        _tenant_resource(session, Lecturer, changes['lecturer_id'], booking.institution_id, 'lecturer')
    if 'student_group_id' in changes:
        _tenant_resource(session, StudentGroup, changes['student_group_id'], booking.institution_id, 'student group')
    if 'campus_id' in changes:
        _tenant_resource(session, Campus, changes['campus_id'], booking.institution_id, 'campus')
    _validate_hard_constraints(session, booking.institution_id, merged)
    for field, value in changes.items():
        setattr(booking, field, value)
    session.add(booking)
    session.commit()
    session.refresh(booking)
    return _booking_dict(booking)


@router.delete('/bookings/{booking_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_booking(
    booking_id: int,
    current_user: User = Depends(require_roles(*RESOURCE_MANAGERS)),
    session: Session = Depends(get_session),
) -> Response:
    booking = _get_booking(session, booking_id, current_user)
    session.delete(booking)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
