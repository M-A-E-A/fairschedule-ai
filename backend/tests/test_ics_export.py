"""S-08 ICS calendar export: VCALENDAR/VEVENT structure, RFC 5545 escaping,
R-007 role scoping, and authentication."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
from app.api.calendar import escape_text, fold, week_anchor
from app.core.db import engine
from app.models import Course, SessionBooking, User
from fastapi.testclient import TestClient
from sqlmodel import Session, delete, select

ESCAPED_NAME = 'Physics; I, Part \\ Two\nEnd'


def _ics(client: TestClient, headers: dict) -> tuple[dict, str]:
    response = client.get('/me/schedule.ics', headers=headers)
    assert response.status_code == 200, response.text
    return response, response.text


def _monday() -> datetime:
    """Monday of the current UTC week (the export's date anchor)."""
    today = datetime.now(UTC).date()
    return datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())


def _events(body: str) -> list[str]:
    """Each VEVENT block of the calendar, in document order."""
    return re.findall(r'BEGIN:VEVENT.*?END:VEVENT', body, flags=re.S)


def _rebuild(parts: list[str]) -> str:
    """Undo line folding: first physical line + de-continued fragments."""
    return parts[0] + ''.join(part[1:] for part in parts[1:])


@pytest.fixture(scope='module', autouse=True)
def _ics_module_rows(client: TestClient, admin_headers: dict):
    """Create the unlinked-faculty account this module needs; remove every row
    this module adds afterwards so later modules see the pristine seed."""
    created = client.post(
        '/admin/users',
        headers=admin_headers,
        json={
            'username': 'ics-unlinked',
            'email': 'ics-unlinked@northbridge.edu',
            'full_name': 'Ivy Unlinked',
            'role': 'faculty',
            'password': 'demo-ics-unlinked',
        },
    )
    assert created.status_code == 201, created.text
    yield
    with Session(engine) as session:
        escape_course_ids = session.exec(select(Course.id).where(Course.code == 'ICS-ESC')).all()
        bookings = session.exec(
            select(SessionBooking).where(SessionBooking.course_id.in_(escape_course_ids))
        ).all()
        for booking in bookings:
            session.delete(booking)
        session.exec(delete(Course).where(Course.code == 'ICS-ESC'))
        session.exec(delete(User).where(User.username == 'ics-unlinked'))
        session.commit()


def test_unauthenticated_requests_are_rejected(client: TestClient):
    assert client.get('/me/schedule.ics').status_code == 401
    assert client.get('/me/schedule.ics', headers={'Authorization': 'Bearer not-a-token'}).status_code == 401


def test_calendar_structure_and_timezone_explicit_times(client: TestClient, admin_headers: dict):
    response, body = _ics(client, admin_headers)

    # Content type and download disposition.
    assert response.headers['content-type'].startswith('text/calendar')
    assert 'schedule.ics' in response.headers['content-disposition']

    # VCALENDAR wrapper.
    assert body.startswith('BEGIN:VCALENDAR\r\n')
    assert body.endswith('END:VCALENDAR\r\n')
    assert 'VERSION:2.0\r\n' in body
    assert 'PRODID:' in body
    # No lone LF: RFC 5545 requires CRLF line endings.
    assert '\n' not in body.replace('\r\n', '')

    # Self-contained timezone definition for the TZID used on every event.
    assert 'BEGIN:VTIMEZONE\r\nTZID:Etc/UTC\r\n' in body
    assert 'END:VTIMEZONE\r\n' in body

    # One VEVENT per session (the administrator sees all 3 seeded sessions).
    events = _events(body)
    assert len(events) == 3

    # Every event carries the required properties, with TZID-qualified times
    # (never floating DTSTART/DTEND).
    for event in events:
        assert re.search(r'UID:fairschedule-\d+@fairschedule-ai\r\n', event)
        assert re.search(r'DTSTAMP:\d{8}T\d{6}Z\r\n', event)
        assert re.search(r'DTSTART;TZID=Etc/UTC:\d{8}T\d{6}\r\n', event)
        assert re.search(r'DTEND;TZID=Etc/UTC:\d{8}T\d{6}\r\n', event)
        assert 'SUMMARY:' in event
    uids = re.findall(r'UID:(\S+)\r', body)
    assert len(uids) == len(set(uids))

    # Session 1 (booking id 1, Monday 09:00-10:30 in the seed) lands on this
    # week's Monday with the stored wall-clock time.
    monday = _monday().strftime('%Y%m%d')
    assert f'DTSTART;TZID=Etc/UTC:{monday}T090000\r\n' in body
    assert f'DTEND;TZID=Etc/UTC:{monday}T103000\r\n' in body

    # Physical lines never exceed the 75-octet fold limit.
    assert max(len(line.encode('utf-8')) for line in body.split('\r\n')) <= 75


def test_student_export_is_scoped_to_own_cohort(client: TestClient, student_headers: dict):
    _, body = _ics(client, student_headers)

    events = _events(body)
    # The seed's CS Year 1 sessions: CS101 (Mon 09:00) + MTH120 (Tue 09:00).
    assert len(events) == 2
    assert 'CS101' in body
    assert 'MTH120' in body
    # DBS201 belongs to CS Year 2 — another cohort is never exported.
    assert 'DBS201' not in body
    tuesday = (_monday() + timedelta(days=1)).strftime('%Y%m%d')
    assert f'DTSTART;TZID=Etc/UTC:{tuesday}T090000\r\n' in body


def test_faculty_export_is_scoped_to_own_lectures(client: TestClient, faculty_headers: dict):
    _, body = _ics(client, faculty_headers)

    # Ada Reed (lecturer link) teaches CS101 only.
    assert len(_events(body)) == 1
    assert 'CS101' in body
    assert 'DBS201' not in body
    assert 'MTH120' not in body


def test_faculty_without_lecturer_link_gets_an_empty_calendar(client: TestClient, module_login):
    headers = module_login(client, 'ics-unlinked', 'demo-ics-unlinked')
    _, body = _ics(client, headers)

    assert body.startswith('BEGIN:VCALENDAR\r\n')
    assert body.endswith('END:VCALENDAR\r\n')
    assert 'BEGIN:VEVENT' not in body


def test_staff_export_covers_the_whole_institution(client: TestClient, operator_headers: dict):
    _, body = _ics(client, operator_headers)

    # Role-first scoping (R-007): an operator gets the institution view.
    assert len(_events(body)) == 3
    assert 'DBS201' in body


def test_special_characters_are_rfc5545_escaped(client: TestClient, student_headers: dict):
    """A course name full of RFC 5545 metacharacters round-trips escaped."""
    with Session(engine) as session:
        course = Course(institution_id=1, code='ICS-ESC', name=ESCAPED_NAME, required_room_type='any')
        session.add(course)
        session.commit()
        session.refresh(course)
        course_id = course.id
        session.add(
            SessionBooking(
                institution_id=1, campus_id=1, course_id=course_id, lecturer_id=1,
                student_group_id=1, room_id=1, day=0, start_minute=630,
                duration_minute=60, status='draft',
            )
        )
        session.commit()

    _, body = _ics(client, student_headers)

    # Backslash, semicolon, comma and newline are each escaped, backslash first.
    assert 'Physics\\; I\\, Part \\\\ Two\\nEnd' in body
    # The joined description fields escape their ';' separators too.
    assert 'Lecturer: Ada Reed\\; Cohort: CS Year 1' in body

    with Session(engine) as session:
        for booking in session.exec(select(SessionBooking).where(SessionBooking.course_id == course_id)).all():
            session.delete(booking)
        session.delete(session.get(Course, course_id))
        session.commit()


# --- unit tests for the pure helpers ---------------------------------------


def test_escape_text_applies_all_rfc5545_rules_in_order():
    assert escape_text('a\\b') == 'a\\\\b'
    assert escape_text('a;b') == 'a\\;b'
    assert escape_text('a,b') == 'a\\,b'
    assert escape_text('a\nb') == 'a\\nb'
    assert escape_text('a\r\nb') == 'a\\nb'
    # Escaping the backslash happens before newline insertion, so '\n' the
    # two-character sequence becomes '\\n' (escaped backslash + n), not '\n'.
    assert escape_text('\\n') == '\\\\n'


def test_fold_respects_the_75_octet_limit_and_reassembles():
    short = 'SUMMARY:short'
    assert fold(short) == [short]

    for long_line in ('DESCRIPTION:' + 'x' * 200, 'SUMMARY:' + 'é' * 60):
        physical = fold(long_line)
        assert all(len(part.encode('utf-8')) <= 75 for part in physical)
        assert len(physical) > 1
        assert all(part.startswith(' ') for part in physical[1:])
        assert _rebuild(physical) == long_line


def test_week_anchor_is_monday_of_the_current_week():
    # 2026-11-12 is a Thursday -> Monday 2026-11-09.
    assert week_anchor(datetime(2026, 11, 12, tzinfo=UTC).date()).isoformat() == '2026-11-09'
    # A Monday anchors to itself.
    assert week_anchor(datetime(2026, 11, 9, tzinfo=UTC).date()).isoformat() == '2026-11-09'
