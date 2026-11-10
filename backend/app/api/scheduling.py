"""Schedule generation, proposals, approval, and the audit trail.

Generation never mutates bookings: it runs the solver, stores the result as a
``ScheduleProposal``, and only an authorised approver (administrator or campus
operator) can apply it. This is the human-in-the-loop boundary required by
docs/PROJECT.md.

Approval revalidates the stored rows against the tenant's *current* data
(``_revalidate_proposal``): between generation and approval bookings and
rooms change freely, so a proposal is applied only after every hard
constraint has been re-checked and any stale reference rejected.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.deps import ensure_tenant, require_roles
from app.core.db import get_session
from app.core.roles import PROPOSAL_APPROVERS, SCHEDULE_MANAGERS
from app.models import (
    AuditEvent,
    Course,
    Room,
    ScheduleProposal,
    SessionBooking,
    StudentGroup,
    User,
)
from app.schemas.scheduling import ScheduleGenerateRequest
from app.services.scheduler import DAY_MINUTES, count_hard_violations, generate_schedule_rows

router = APIRouter(tags=['scheduling'])


@router.post('/schedules/generate')
def generate_schedule(
    payload: ScheduleGenerateRequest,
    current_user: User = Depends(require_roles(*SCHEDULE_MANAGERS)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    ensure_tenant(current_user, payload.institution_id)
    bookings = session.exec(
        select(SessionBooking).where(
            SessionBooking.institution_id == payload.institution_id,
            SessionBooking.campus_id == payload.campus_id,
        )
    ).all()
    rooms = session.exec(
        select(Room).where(Room.institution_id == payload.institution_id, Room.campus_id == payload.campus_id)
    ).all()

    course_by_id = {
        row.id: row for row in session.exec(select(Course).where(Course.institution_id == payload.institution_id)).all()
    }
    group_by_id = {
        row.id: row
        for row in session.exec(select(StudentGroup).where(StudentGroup.institution_id == payload.institution_id)).all()
    }

    sessions = []
    for booking in bookings:
        course = course_by_id.get(booking.course_id)
        group = group_by_id.get(booking.student_group_id)
        sessions.append({
            'id': booking.id,
            'course': course.name if course else 'Course',
            'course_code': course.code if course else '',
            'required_room_type': course.required_room_type if course else 'any',
            'lecturer_id': booking.lecturer_id,
            'student_group_id': booking.student_group_id,
            'headcount': group.size if group else 0,
            'duration_minute': booking.duration_minute,
            'original_day': booking.day,
            'original_start_minute': booking.start_minute,
            'original_room_id': booking.room_id,
            'day_start': payload.day_start,
            'day_end': payload.day_end,
        })
    room_rows = [
        {'id': room.id, 'name': room.name, 'capacity': room.capacity, 'room_type': room.room_type}
        for room in rooms
    ]

    result = generate_schedule_rows(
        sessions,
        room_rows,
        institution_id=payload.institution_id,
        campus_id=payload.campus_id,
        days=payload.days,
        day_start=payload.day_start,
        day_end=payload.day_end,
        allow_time_change=payload.allow_time_change,
        time_limit_seconds=payload.time_limit_seconds,
    )

    proposal = ScheduleProposal(
        institution_id=payload.institution_id,
        campus_id=payload.campus_id,
        owner_email=current_user.email,
        summary=f"Schedule generation finished with status {result['status']} "
        f'({len(result["rows"])}/{len(sessions)} sessions placed)',
        json_payload=json.dumps(
            {
                'rows': result['rows'],
                'metrics': result['metrics'],
                # Approval re-runs every hard constraint against *current*
                # data, so the generation parameters travel with the rows.
                'params': {
                    'days': payload.days,
                    'day_start': payload.day_start,
                    'day_end': payload.day_end,
                    'allow_time_change': payload.allow_time_change,
                },
            }
        ),
        approved=False,
    )
    session.add(proposal)
    session.add(
        AuditEvent(
            institution_id=payload.institution_id,
            user_email=current_user.email,
            event_type='schedule_generated',
            message=f"Generated draft schedule (status {result['status']}, "
            f"violations {result['metrics']['hard_constraint_violations']})",
        )
    )
    session.commit()
    session.refresh(proposal)

    return {
        'status': result['status'],
        'schedule': result['rows'],
        'metrics': result['metrics'],
        'proposal_id': proposal.id,
    }


@router.get('/proposals')
def list_proposals(
    current_user: User = Depends(require_roles(*SCHEDULE_MANAGERS)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = session.exec(
        select(ScheduleProposal).where(ScheduleProposal.institution_id == current_user.institution_id)
    ).all()
    return [
        {
            'id': proposal.id,
            'campus_id': proposal.campus_id,
            'owner_email': proposal.owner_email,
            'summary': proposal.summary,
            'approved': proposal.approved,
            'metrics': json.loads(proposal.json_payload).get('metrics', {}),
        }
        for proposal in sorted(rows, key=lambda item: item.id, reverse=True)
    ]


def _revalidate_proposal(session: Session, proposal: ScheduleProposal, rows: list[dict[str, Any]]) -> None:
    """Re-run every hard constraint against *current* data before approval.

    docs/PROJECT.md requires that any proposed change be validated again by
    the backend before approval: between generation and approval the tenant's
    bookings can be created, edited, deleted, or moved to another campus, and
    rooms can shrink, change type, or disappear. Stored solver rows are stale
    until proven otherwise. Raises 409 when any violation or stale reference
    is found; the caller must not apply anything in that case.
    """
    institution_id = proposal.institution_id
    params = json.loads(proposal.json_payload).get('params', {})
    day_start = params.get('day_start', 0)
    day_end = params.get('day_end', DAY_MINUTES)

    rooms = session.exec(select(Room).where(Room.institution_id == institution_id)).all()
    room_by_id = {room.id: room for room in rooms}
    course_by_id = {
        row.id: row for row in session.exec(select(Course).where(Course.institution_id == institution_id)).all()
    }
    group_by_id = {
        row.id: row
        for row in session.exec(select(StudentGroup).where(StudentGroup.institution_id == institution_id)).all()
    }
    bookings = session.exec(
        select(SessionBooking).where(SessionBooking.institution_id == institution_id)
    ).all()
    booking_by_id = {booking.id: booking for booking in bookings}
    row_by_session = {row['session_id']: row for row in rows}

    # Stale references: sessions deleted or moved off the proposal's campus
    # since generation, and rooms deleted or moved off that campus.
    for row in rows:
        booking = booking_by_id.get(row['session_id'])
        if booking is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'proposal is stale: session {row["session_id"]} no longer exists; '
                'regenerate the schedule',
            )
        if booking.campus_id != proposal.campus_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'proposal is stale: session {row["session_id"]} moved to another campus '
                'after generation; regenerate the schedule',
            )
        room = room_by_id.get(row['room_id'])
        if room is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'proposal is stale: room {row["room_id"]} no longer exists; regenerate the schedule',
            )
        if room.campus_id != proposal.campus_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'proposal is stale: room {room.name} is no longer on the proposal\'s campus; '
                'regenerate the schedule',
            )

    # Reconstruct the post-application state: the tenant's current bookings
    # with each proposal row applied on top, then check the whole state.
    sessions = []
    state_rows = []
    for booking in bookings:
        row = row_by_session.get(booking.id)
        course = course_by_id.get(booking.course_id)
        group = group_by_id.get(booking.student_group_id)
        sessions.append(
            {
                'id': booking.id,
                'headcount': group.size if group else 0,
                'required_room_type': course.required_room_type if course else 'any',
                'lecturer_id': booking.lecturer_id,
                'student_group_id': booking.student_group_id,
                'duration_minute': booking.duration_minute,
                # Only the sessions this proposal moves are bound by the
                # generation window; untouched bookings keep their stored
                # times, which write-time enforcement already validated.
                'day_start': day_start if row is not None else 0,
                'day_end': day_end if row is not None else DAY_MINUTES,
            }
        )
        state_rows.append(
            {
                'session_id': booking.id,
                'room_id': row['room_id'] if row is not None else booking.room_id,
                'day': row['day'] if row is not None else booking.day,
                'start_minute': row['start_minute'] if row is not None else booking.start_minute,
                'duration_minute': booking.duration_minute,
            }
        )
    room_rows = [
        {'id': room.id, 'capacity': room.capacity, 'room_type': room.room_type} for room in rooms
    ]
    violations = count_hard_violations(sessions, room_rows, state_rows)
    if violations:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'proposal conflicts with current data ({violations} hard-constraint violation(s)); '
            'regenerate the schedule',
        )


@router.post('/proposals/{proposal_id}/approve')
def approve_proposal(
    proposal_id: int,
    current_user: User = Depends(require_roles(*PROPOSAL_APPROVERS)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    proposal = session.get(ScheduleProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='proposal not found')
    ensure_tenant(current_user, proposal.institution_id)
    if proposal.approved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='proposal already approved')

    payload = json.loads(proposal.json_payload)
    rows = payload.get('rows', [])
    try:
        _revalidate_proposal(session, proposal, rows)
    except HTTPException as exc:
        # The refusal itself is part of the audit trail (docs/PROJECT.md).
        session.add(
            AuditEvent(
                institution_id=proposal.institution_id,
                user_email=current_user.email,
                event_type='proposal_rejected',
                message=f'Rejected proposal {proposal.id}: {exc.detail}',
            )
        )
        session.commit()
        raise

    updated = 0
    for row in rows:
        booking = session.get(SessionBooking, row['session_id'])
        if booking is None or booking.institution_id != proposal.institution_id:
            continue
        booking.room_id = row['room_id']
        booking.day = row['day']
        booking.start_minute = row['start_minute']
        booking.status = 'published'
        session.add(booking)
        updated += 1

    proposal.approved = True
    session.add(proposal)
    session.add(
        AuditEvent(
            institution_id=proposal.institution_id,
            user_email=current_user.email,
            event_type='proposal_approved',
            message=f'Approved proposal {proposal.id}: {updated} session(s) updated and published '
            '(hard constraints revalidated against current data)',
        )
    )
    session.commit()
    return {'approved': True, 'proposal_id': proposal.id, 'updated_sessions': updated}


@router.get('/audit-events')
def list_audit_events(
    current_user: User = Depends(require_roles('administrator')),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = session.exec(
        select(AuditEvent).where(AuditEvent.institution_id == current_user.institution_id)
    ).all()
    return [
        {
            'id': event.id,
            'user_email': event.user_email,
            'event_type': event.event_type,
            'message': event.message,
        }
        for event in sorted(rows, key=lambda item: item.id, reverse=True)
    ]
