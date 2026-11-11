"""Schedule generation, proposals, approval, the audit trail, and the
timetable publish lifecycle (S-06).

Generation never mutates bookings: it runs the solver, stores the result as a
``ScheduleProposal``, and only an authorised approver (administrator or campus
operator) can apply it. This is the human-in-the-loop boundary required by
docs/PROJECT.md.

Approval revalidates the stored rows against the tenant's *current* data
(``_revalidate_proposal``): between generation and approval bookings and
rooms change freely, so a proposal is applied only after every hard
constraint has been re-checked and any stale reference rejected.

Publishing freezes a named, versioned snapshot of the tenant's whole
timetable in ``TimetableVersion``; the snapshot is immutable, so any previous
version stays queryable exactly as published, and the diff endpoint compares
the live draft against the latest published version.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.deps import ensure_tenant, require_roles
from app.core.config import get_settings
from app.core.db import get_session
from app.core.roles import PROPOSAL_APPROVERS, SCHEDULE_MANAGERS
from app.models import (
    AuditEvent,
    Course,
    Room,
    ScheduleProposal,
    SessionBooking,
    StudentGroup,
    TimetableVersion,
    User,
)
from app.schemas.scheduling import ScheduleGenerateRequest, TimetablePublishRequest
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
        # S-01: the wall-clock budget is env-configured
        # (SOLVER_TIME_LIMIT_SECONDS, default 10s); a request may override it
        # explicitly. The solver must return within the budget whatever the
        # instance size, reporting UNKNOWN honestly when it cannot finish.
        time_limit_seconds=payload.time_limit_seconds
        if payload.time_limit_seconds is not None
        else get_settings().solver_time_limit_seconds,
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


# --- S-06: timetable publish lifecycle --------------------------------------


def _booking_snapshot(booking: SessionBooking) -> dict[str, Any]:
    """The frozen row shape stored inside a TimetableVersion payload.

    Fields only (no joined labels): the snapshot must stay meaningful even
    after the referenced course/lecturer/group/room rows are edited or
    deleted — a published version is history, not a live join.
    """
    return {
        'id': booking.id,
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


@router.post('/institutions/{institution_id}/timetable/publish')
def publish_timetable(
    institution_id: int,
    payload: TimetablePublishRequest,
    current_user: User = Depends(require_roles(*PROPOSAL_APPROVERS)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Freeze the tenant's current timetable as a named, versioned snapshot.

    Only proposal approvers (administrator, campus operator) may publish —
    the same human-in-the-loop boundary as proposal approval. Publishing
    copies the current booking rows; it never mutates them, and a stored
    version is never rewritten afterwards.
    """
    ensure_tenant(current_user, institution_id)
    bookings = session.exec(
        select(SessionBooking).where(SessionBooking.institution_id == institution_id)
    ).all()
    existing_versions = session.exec(
        select(TimetableVersion).where(TimetableVersion.institution_id == institution_id)
    ).all()
    version_number = max((row.version for row in existing_versions), default=0) + 1

    version_row = TimetableVersion(
        institution_id=institution_id,
        version=version_number,
        label=payload.label.strip() or f'Version {version_number}',
        published_by_email=current_user.email,
        published_at=datetime.now(UTC).replace(tzinfo=None),
        json_payload=json.dumps([_booking_snapshot(booking) for booking in bookings]),
    )
    session.add(version_row)
    session.add(
        AuditEvent(
            institution_id=institution_id,
            user_email=current_user.email,
            event_type='timetable_published',
            message=f'Published timetable version {version_number} '
            f'"{version_row.label}" ({len(bookings)} session(s))',
        )
    )
    session.commit()
    session.refresh(version_row)
    return {
        'id': version_row.id,
        'version': version_row.version,
        'label': version_row.label,
        'published_by_email': version_row.published_by_email,
        'published_at': version_row.published_at.isoformat(),
        'session_count': len(bookings),
    }


@router.get('/institutions/{institution_id}/timetable/versions')
def list_timetable_versions(
    institution_id: int,
    current_user: User = Depends(require_roles(*SCHEDULE_MANAGERS)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Published versions of the tenant's timetable, newest first.

    Visible to the same staff roles that may read the full timetable;
    students never see institution-wide data.
    """
    ensure_tenant(current_user, institution_id)
    rows = session.exec(
        select(TimetableVersion).where(TimetableVersion.institution_id == institution_id)
    ).all()
    return [
        {
            'id': row.id,
            'version': row.version,
            'label': row.label,
            'published_by_email': row.published_by_email,
            'published_at': row.published_at.isoformat(),
            'session_count': len(json.loads(row.json_payload)),
        }
        for row in sorted(rows, key=lambda item: item.version, reverse=True)
    ]


@router.get('/institutions/{institution_id}/timetable/diff')
def timetable_diff(
    institution_id: int,
    current_user: User = Depends(require_roles(*SCHEDULE_MANAGERS)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Diff the current draft against the currently published version.

    Added: sessions booked since the last publish. Removed: sessions the
    last publish contains that no longer exist. Moved: sessions present in
    both whose room, day, start time, or duration changed. If nothing was
    ever published the whole draft counts as added and ``published_version``
    is null (an honest "nothing to compare against" rather than a fake diff).
    """
    ensure_tenant(current_user, institution_id)
    published_rows = session.exec(
        select(TimetableVersion).where(TimetableVersion.institution_id == institution_id)
    ).all()
    draft = {
        booking.id: _booking_snapshot(booking)
        for booking in session.exec(
            select(SessionBooking).where(SessionBooking.institution_id == institution_id)
        ).all()
    }

    if not published_rows:
        return {
            'institution_id': institution_id,
            'published_version': None,
            'published_label': None,
            'draft_session_count': len(draft),
            'added': sorted(draft.values(), key=lambda row: row['id']),
            'removed': [],
            'moved': [],
        }

    latest = max(published_rows, key=lambda row: row.version)
    published = {row['id']: row for row in json.loads(latest.json_payload)}

    added = [draft[key] for key in draft.keys() - published.keys()]
    removed = [published[key] for key in published.keys() - draft.keys()]
    moved = []
    for session_id in draft.keys() & published.keys():
        before = published[session_id]
        after = draft[session_id]
        changed = any(
            before[field] != after[field]
            for field in ('room_id', 'day', 'start_minute', 'duration_minute')
        )
        if changed:
            moved.append({'id': session_id, 'from': before, 'to': after})

    return {
        'institution_id': institution_id,
        'published_version': latest.version,
        'published_label': latest.label,
        'draft_session_count': len(draft),
        'added': sorted(added, key=lambda row: row['id']),
        'removed': sorted(removed, key=lambda row: row['id']),
        'moved': sorted(moved, key=lambda row: row['id']),
    }
