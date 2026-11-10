"""Room CRUD. Reads are open to every role of the tenant; mutations require
campus-operator or administrator role.

Room edits never invalidate existing bookings: capacity, room type, and
campus changes are revalidated against every booking that references the
room, so the hard constraints that ``bookings.py`` enforces at write time
cannot be broken afterwards through this API.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from app.api.deps import ensure_tenant, get_current_user, require_roles
from app.core.db import get_session
from app.core.roles import ROOM_MANAGERS
from app.models import Campus, Course, Room, SessionBooking, StudentGroup, User
from app.schemas.scheduling import RoomCreateRequest, RoomUpdateRequest

router = APIRouter(tags=['rooms'])


def _room_dict(room: Room) -> dict[str, Any]:
    return {
        'id': room.id,
        'institution_id': room.institution_id,
        'campus_id': room.campus_id,
        'name': room.name,
        'capacity': room.capacity,
        'room_type': room.room_type,
        'equipment': room.equipment,
    }


def _get_room(session: Session, room_id: int, user: User) -> Room:
    room = session.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='room not found')
    ensure_tenant(user, room.institution_id)
    return room


@router.get('/institutions/{institution_id}/rooms')
def list_rooms(
    institution_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    ensure_tenant(current_user, institution_id)
    rows = session.exec(select(Room).where(Room.institution_id == institution_id)).all()
    return [_room_dict(room) for room in rows]


@router.post('/institutions/{institution_id}/rooms', status_code=status.HTTP_201_CREATED)
def create_room(
    institution_id: int,
    payload: RoomCreateRequest,
    current_user: User = Depends(require_roles(*ROOM_MANAGERS)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    ensure_tenant(current_user, institution_id)
    campus = session.get(Campus, payload.campus_id)
    if campus is None or campus.institution_id != institution_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='campus does not belong to this institution')
    room = Room(
        institution_id=institution_id,
        campus_id=payload.campus_id,
        name=payload.name,
        capacity=payload.capacity,
        room_type=payload.room_type,
        equipment=payload.equipment,
    )
    session.add(room)
    session.commit()
    session.refresh(room)
    return _room_dict(room)


def _validate_room_change(session: Session, room: Room, changes: dict[str, Any]) -> None:
    """Refuse edits that would leave existing bookings violating constraints.

    The capacity and room-type hard constraints are enforced at booking-write
    time; a room edit is the other path by which they could be broken, so it
    is revalidated against every booking that references the room. The
    documented policy is to reject with 409 and name the offending booking —
    the operator must move or reassign those sessions first.
    """
    bookings = session.exec(select(SessionBooking).where(SessionBooking.room_id == room.id)).all()
    if not bookings:
        return
    course_by_id = {
        row.id: row for row in session.exec(select(Course).where(Course.institution_id == room.institution_id)).all()
    }
    group_by_id = {
        row.id: row
        for row in session.exec(select(StudentGroup).where(StudentGroup.institution_id == room.institution_id)).all()
    }
    for booking in bookings:
        if 'campus_id' in changes and changes['campus_id'] != room.campus_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"room is referenced by booking {booking.id} on its current campus; "
                'move those sessions first',
            )
        if 'capacity' in changes:
            group = group_by_id.get(booking.student_group_id)
            needed = group.size if group else 0
            if changes['capacity'] < needed:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f'capacity violated: {room.name} would seat {changes["capacity"]}, '
                    f'but booking {booking.id} needs {needed} seats',
                )
        if 'room_type' in changes:
            course = course_by_id.get(booking.course_id)
            required = course.required_room_type if course else 'any'
            if required not in ('any', '', None) and changes['room_type'] != required:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f'room type violated: booking {booking.id} requires {required}, '
                    f'{room.name} would become {changes["room_type"]}',
                )


@router.patch('/rooms/{room_id}')
def update_room(
    room_id: int,
    payload: RoomUpdateRequest,
    current_user: User = Depends(require_roles(*ROOM_MANAGERS)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    room = _get_room(session, room_id, current_user)
    changes = payload.model_dump(exclude_unset=True)
    if 'campus_id' in changes:
        campus = session.get(Campus, changes['campus_id'])
        if campus is None or campus.institution_id != room.institution_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail='campus does not belong to this institution'
            )
    if {'capacity', 'room_type', 'campus_id'} & changes.keys():
        _validate_room_change(session, room, changes)
    for field, value in changes.items():
        setattr(room, field, value)
    session.add(room)
    session.commit()
    session.refresh(room)
    return _room_dict(room)


@router.delete('/rooms/{room_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_room(
    room_id: int,
    current_user: User = Depends(require_roles(*ROOM_MANAGERS)),
    session: Session = Depends(get_session),
) -> Response:
    room = _get_room(session, room_id, current_user)
    bookings = session.exec(select(SessionBooking).where(SessionBooking.room_id == room_id)).all()
    if bookings:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'room is referenced by {len(bookings)} booking(s); reassign them first',
        )
    session.delete(room)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
