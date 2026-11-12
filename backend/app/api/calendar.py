"""ICS calendar export for the requesting user's own schedule (S-08).

``GET /me/schedule.ics`` serves a ``text/calendar`` VCALENDAR with one VEVENT
per session of the caller's own role-scoped schedule. The events are built
from the exact payload of ``GET /me/schedule`` (``build_schedule_payload``:
student → cohort, faculty → own lectures, staff → institution — the R-007
scoping rules), so the JSON view and the calendar export cannot drift apart.

Format decisions:

* **Timezone-explicit times.** Bookings store naive wall-clock minutes per
  weekday. The export anchors them to Monday of the current UTC week and
  writes ``DTSTART;TZID=Etc/UTC:…`` / ``DTEND;TZID=Etc/UTC:…`` local times,
  with a self-contained ``VTIMEZONE`` component for that TZID — never
  floating (unqualified) times.
* **RFC 5545 TEXT escaping.** Backslash, semicolon, comma and newlines in
  SUMMARY/DESCRIPTION/LOCATION are escaped per section 3.3.11.
* **Line folding.** Every physical line is folded to at most 75 octets with
  CRLF + space continuations (section 7.2.9), so long course names survive
  strict parsers.
* **UID** is derived from the immutable booking id, so re-exporting the same
  schedule yields the same event identity.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlmodel import Session

from app.api.dashboard import build_schedule_payload
from app.api.deps import get_current_user
from app.core.db import get_session
from app.models import User

router = APIRouter(tags=['calendar'])

PRODID = '-//FairSchedule AI//FairSchedule AI schedule//EN'
TZID = 'Etc/UTC'
# Physical lines must not exceed 75 octets (RFC 5545 §7.2.9).
FOLD_OCTETS = 75
_EVENT_TIME_FORMAT = '%Y%m%dT%H%M%S'


def escape_text(value: str) -> str:
    """Escape a TEXT value per RFC 5545 §3.3.11 (backslash first)."""
    return (
        value.replace('\\', '\\\\')
        .replace(';', '\\;')
        .replace(',', '\\,')
        .replace('\r\n', '\n')
        .replace('\r', '\n')
        .replace('\n', '\\n')
    )


def fold(line: str) -> list[str]:
    """Fold one logical line into physical lines of at most 75 octets.

    Continuation lines begin with a single space (which counts toward the
    limit). Splitting happens on octet boundaries without breaking a
    multi-byte UTF-8 character.
    """
    encoded = line.encode('utf-8')
    if len(encoded) <= FOLD_OCTETS:
        return [line]
    chunks: list[str] = []
    start = 0
    limit = FOLD_OCTETS
    while start < len(encoded):
        end = min(start + limit, len(encoded))
        while end < len(encoded) and (encoded[end] & 0xC0) == 0x80:
            end -= 1
        if end == start:  # pragma: no cover - no UTF-8 character exceeds the limit
            end = start + limit
        chunks.append(encoded[start:end].decode('utf-8'))
        start = end
        limit = FOLD_OCTETS - 1  # continuation lines spend one octet on the leading space
    return [chunks[0], *(f' {chunk}' for chunk in chunks[1:])]


def week_anchor(anchor: date | None = None) -> date:
    """Monday of the week containing ``anchor`` (UTC "now" by default)."""
    today = anchor if anchor is not None else datetime.now(UTC).date()
    return today - timedelta(days=today.weekday())


def build_ics(payload: dict[str, Any], generated_at: datetime | None = None) -> str:
    """Render a role-scoped schedule payload as an RFC 5545 VCALENDAR."""
    now = generated_at if generated_at is not None else datetime.now(UTC)
    monday = week_anchor(now.date())
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        f'PRODID:{PRODID}',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'BEGIN:VTIMEZONE',
        f'TZID:{TZID}',
        'BEGIN:STANDARD',
        'DTSTART:19700101T000000',
        'TZOFFSETFROM:+0000',
        'TZOFFSETTO:+0000',
        'TZNAME:UTC',
        'END:STANDARD',
        'END:VTIMEZONE',
    ]
    dtstamp = now.strftime('%Y%m%dT%H%M%SZ')

    for session in payload.get('sessions', []):
        day = session['day']
        event_date = monday + timedelta(days=day)
        event_start = datetime.combine(event_date, datetime.min.time()) + timedelta(
            minutes=session['start_minute']
        )
        event_end = datetime.combine(event_date, datetime.min.time()) + timedelta(
            minutes=session['end_minute']
        )
        summary = f"{session['course_code']} {session['course_name']}".strip() or 'Session'
        description = (
            f"Lecturer: {session['lecturer_name'] or '—'}; "
            f"Cohort: {session['student_group_name'] or '—'}"
        )
        lines += [
            'BEGIN:VEVENT',
            # Stable identity: the booking id never changes for a session.
            f"UID:fairschedule-{session['id']}@fairschedule-ai",
            f'DTSTAMP:{dtstamp}',
            f'DTSTART;TZID={TZID}:{event_start.strftime(_EVENT_TIME_FORMAT)}',
            f'DTEND;TZID={TZID}:{event_end.strftime(_EVENT_TIME_FORMAT)}',
            f'SUMMARY:{escape_text(summary)}',
            f'DESCRIPTION:{escape_text(description)}',
            f'LOCATION:{escape_text(str(session["room_name"] or ""))}',
            'END:VEVENT',
        ]
    lines.append('END:VCALENDAR')

    folded = [part for line in lines for part in fold(line)]
    return '\r\n'.join(folded) + '\r\n'


@router.get('/me/schedule.ics')
def my_schedule_ics(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    """Download the caller's own schedule as an ICS calendar.

    Same role scoping as ``GET /me/schedule`` (R-007): students receive
    their cohort's sessions, faculty their own lectures, operators and
    administrators the whole institution. Unauthenticated requests are
    refused with 401 by the shared dependency.
    """
    ics = build_ics(build_schedule_payload(session, current_user))
    return Response(
        content=ics,
        media_type='text/calendar',
        headers={'Content-Disposition': 'attachment; filename="schedule.ics"'},
    )
