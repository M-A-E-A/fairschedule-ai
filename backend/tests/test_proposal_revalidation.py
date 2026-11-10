"""Round 2 (R-001): proposal approval revalidates stored solver rows.

docs/PROJECT.md requires any proposed change to be validated again by the
backend before approval. Between generation and approval the tenant's data
changes — bookings are created, edited, deleted, or moved to another campus
and rooms shrink or change type — so approval must reconstruct the
post-application state from *current* data and re-run every hard constraint
before a single row is applied.
"""

from __future__ import annotations

import json

import pytest
from app.core.db import engine
from app.models import Room, ScheduleProposal
from fastapi.testclient import TestClient
from sqlmodel import Session


@pytest.fixture(scope='module')
def admin_headers(client, module_login):
    return module_login(client, 'admin')


@pytest.fixture(scope='module')
def ids(client: TestClient, admin_headers: dict[str, str]) -> dict:
    rooms = {room['name']: room['id'] for room in client.get('/institutions/1/rooms', headers=admin_headers).json()}
    courses = {c['code']: c['id'] for c in client.get('/institutions/1/courses', headers=admin_headers).json()}
    lecturers = {
        row['name']: row['id'] for row in client.get('/institutions/1/lecturers', headers=admin_headers).json()
    }
    groups = {g['name']: g['id'] for g in client.get('/institutions/1/student-groups', headers=admin_headers).json()}
    campuses = {c['slug']: c['id'] for c in client.get('/institutions/1/campuses', headers=admin_headers).json()}
    return {'rooms': rooms, 'courses': courses, 'lecturers': lecturers, 'groups': groups, 'campuses': campuses}


def _generate(client: TestClient, headers: dict[str, str], **overrides) -> dict:
    payload = {'institution_id': 1, 'campus_id': 1}
    payload.update(overrides)
    response = client.post('/schedules/generate', headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _reseed_main_bookings(client: TestClient, headers: dict[str, str], ids: dict) -> None:
    """Return Northbridge bookings to the seeded three, exactly as in seed.py.

    The seeded sessions are deleted and re-created through the public API, so
    later test modules (which generate and approve proposals of their own)
    always start from the seeded positions and `draft` status.
    """
    for booking in client.get('/institutions/1/bookings', headers=headers).json():
        assert client.delete(f"/bookings/{booking['id']}", headers=headers).status_code == 204
    seeded = [
        {
            'campus_id': ids['campuses']['main'],
            'course_id': ids['courses']['CS101'],
            'lecturer_id': ids['lecturers']['Ada Reed'],
            'student_group_id': ids['groups']['CS Year 1'],
            'room_id': ids['rooms']['A101'],
            'day': 0,
            'start_minute': 540,
            'duration_minute': 90,
        },
        {
            'campus_id': ids['campuses']['main'],
            'course_id': ids['courses']['DBS201'],
            'lecturer_id': ids['lecturers']['Sam Chen'],
            'student_group_id': ids['groups']['CS Year 2'],
            'room_id': ids['rooms']['B204'],
            'day': 0,
            'start_minute': 600,
            'duration_minute': 90,
        },
        {
            'campus_id': ids['campuses']['main'],
            'course_id': ids['courses']['MTH120'],
            'lecturer_id': ids['lecturers']['Priya Nair'],
            'student_group_id': ids['groups']['CS Year 1'],
            'room_id': ids['rooms']['C315'],
            'day': 1,
            'start_minute': 540,
            'duration_minute': 90,
        },
    ]
    for spec in seeded:
        created = client.post('/institutions/1/bookings', headers=headers, json=spec)
        assert created.status_code == 201, created.text


def test_approval_rejects_booking_created_after_generation(client: TestClient, admin_headers, ids):
    """A booking written between generation and approval must block approval.

    The generation window is narrowed to 8:00-10:00 so the solver must move
    the seeded 9:00/10:00 sessions to earlier slots; a booking is then placed
    exactly on one of those target slots. Applying the proposal would
    double-book the room, so approval must be refused with 409.
    """
    generated = _generate(client, admin_headers, day_start=480, day_end=600)
    assert generated['metrics']['hard_constraint_violations'] == 0
    row = generated['schedule'][0]

    current = {b['id']: b for b in client.get('/institutions/1/bookings', headers=admin_headers).json()}
    original = current[row['session_id']]
    # The narrowed window really did move this session off its stored slot.
    assert (row['day'], row['start_minute']) != (original['day'], original['start_minute'])

    # A booking that conflicts only with the *proposal's target* slot (the
    # room is free at that time in the current data, so the write succeeds).
    collision = client.post(
        '/institutions/1/bookings',
        headers=admin_headers,
        json={
            'campus_id': original['campus_id'],
            'course_id': ids['courses']['MTH120'],
            'lecturer_id': ids['lecturers']['Priya Nair'],
            'student_group_id': ids['groups']['CS Year 2'],
            'room_id': row['room_id'],
            'day': row['day'],
            'start_minute': row['start_minute'],
            'duration_minute': 60,
        },
    )
    assert collision.status_code == 201, collision.text

    refused = client.post(f"/proposals/{generated['proposal_id']}/approve", headers=admin_headers)
    assert refused.status_code == 409, refused.text
    assert 'conflicts with current data' in refused.json()['detail']

    # The refusal is part of the audit trail.
    audit = client.get('/audit-events', headers=admin_headers).json()
    assert any(event['event_type'] == 'proposal_rejected' for event in audit)

    # Nothing was applied: the session is untouched and the proposal is open.
    after = {b['id']: b for b in client.get('/institutions/1/bookings', headers=admin_headers).json()}
    assert after[row['session_id']]['day'] == original['day']
    assert after[row['session_id']]['start_minute'] == original['start_minute']
    proposals = client.get('/proposals', headers=admin_headers).json()
    assert next(p for p in proposals if p['id'] == generated['proposal_id'])['approved'] is False

    # With the collision removed, the very same proposal applies cleanly —
    # and its rows are revalidated once more before they are written.
    assert client.delete(f"/bookings/{collision.json()['id']}", headers=admin_headers).status_code == 204
    approved = client.post(f"/proposals/{generated['proposal_id']}/approve", headers=admin_headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()['updated_sessions'] >= 3

    _reseed_main_bookings(client, admin_headers, ids)


def test_approval_rejects_session_deleted_after_generation(client: TestClient, admin_headers, ids):
    """A proposal row pointing at a deleted session is a stale reference."""
    generated = _generate(client, admin_headers)
    victim = next(
        b for b in client.get('/institutions/1/bookings', headers=admin_headers).json() if b['day'] == 1
    )
    assert client.delete(f"/bookings/{victim['id']}", headers=admin_headers).status_code == 204

    refused = client.post(f"/proposals/{generated['proposal_id']}/approve", headers=admin_headers)
    assert refused.status_code == 409, refused.text
    assert 'no longer exists' in refused.json()['detail']

    proposals = client.get('/proposals', headers=admin_headers).json()
    assert next(p for p in proposals if p['id'] == generated['proposal_id'])['approved'] is False

    _reseed_main_bookings(client, admin_headers, ids)


def test_approval_rejects_session_moved_to_another_campus(client: TestClient, admin_headers, ids):
    """A session moved to another campus after generation makes the proposal
    stale: its rows would put a main-campus room on a tech-campus booking."""
    generated = _generate(client, admin_headers)
    victim = next(
        b
        for b in client.get('/institutions/1/bookings', headers=admin_headers).json()
        if b['course_id'] == ids['courses']['MTH120']
    )
    moved = client.patch(
        f"/bookings/{victim['id']}",
        headers=admin_headers,
        json={'campus_id': ids['campuses']['tech-park'], 'room_id': ids['rooms']['T12']},
    )
    assert moved.status_code == 200, moved.text

    refused = client.post(f"/proposals/{generated['proposal_id']}/approve", headers=admin_headers)
    assert refused.status_code == 409, refused.text
    assert 'moved to another campus' in refused.json()['detail']

    _reseed_main_bookings(client, admin_headers, ids)


def test_approval_rejects_room_moved_off_proposal_campus(client: TestClient, admin_headers, ids):
    """A row whose room is no longer on the proposal's campus is stale.

    The rooms API now refuses campus moves for rooms with bookings (see the
    R-003 tests), so this corruption is injected directly into the stored
    proposal payload to represent a room that drifted after generation.
    """
    generated = _generate(client, admin_headers)
    with Session(engine) as db:
        proposal = db.get(ScheduleProposal, generated['proposal_id'])
        payload = json.loads(proposal.json_payload)
        payload['rows'][0]['room_id'] = ids['rooms']['T12']  # a Tech Park room
        proposal.json_payload = json.dumps(payload)
        db.add(proposal)
        db.commit()

    refused = client.post(f"/proposals/{generated['proposal_id']}/approve", headers=admin_headers)
    assert refused.status_code == 409, refused.text
    assert "no longer on the proposal's campus" in refused.json()['detail']


def test_approval_rejects_room_shrunk_after_generation(client: TestClient, admin_headers, ids):
    """A room shrunk below a group's size must invalidate the proposal.

    The rooms API now refuses such a shrink while bookings exist (R-003), so
    the drift is injected directly in the database — the exact legacy state
    the approval-time revalidation exists to catch.
    """
    generated = _generate(client, admin_headers)
    row = generated['schedule'][0]
    original_capacity = next(
        room['capacity'] for room in client.get('/institutions/1/rooms', headers=admin_headers).json()
        if room['id'] == row['room_id']
    )

    with Session(engine) as db:
        room_row = db.get(Room, row['room_id'])
        room_row.capacity = 5  # smaller than any cohort
        db.add(room_row)
        db.commit()

    refused = client.post(f"/proposals/{generated['proposal_id']}/approve", headers=admin_headers)
    assert refused.status_code == 409, refused.text
    assert 'conflicts with current data' in refused.json()['detail']

    with Session(engine) as db:
        room_row = db.get(Room, row['room_id'])
        room_row.capacity = original_capacity
        db.add(room_row)
        db.commit()
