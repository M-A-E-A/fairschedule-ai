"""Schedule generation, proposals, approval, and the audit trail.

Generation never mutates bookings: it runs the solver, stores the result as a
``ScheduleProposal``, and only an authorised approver (administrator or campus
operator) can apply it. This is the human-in-the-loop boundary required by
docs/PROJECT.md.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.deps import ensure_tenant, get_current_user, require_roles
from app.core.db import get_session
from app.core.roles import PROPOSAL_APPROVERS, SCHEDULE_MANAGERS
from app.models import (
    AuditEvent,
    Course,
    Lecturer,
    Room,
    ScheduleProposal,
    SessionBooking,
    StudentGroup,
    User,
)
from app.schemas.scheduling import ScheduleGenerateRequest
from app.services.scheduler import generate_schedule_rows

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

    course_by_id = {row.id: row for row in session.exec(select(Course)).all()}
    group_by_id = {row.id: row for row in session.exec(select(StudentGroup)).all()}

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
        json_payload=json.dumps({'rows': result['rows'], 'metrics': result['metrics']}),
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
            message=f'Approved proposal {proposal.id}: {updated} session(s) updated and published',
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
