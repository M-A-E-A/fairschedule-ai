"""Schedule generation: solver constraints, proposals, approval/publish, audit."""

from __future__ import annotations

import pytest


@pytest.fixture(scope='module')
def faculty_headers(client, module_login):
    return module_login(client, 'faculty')


@pytest.fixture(scope='module')
def operator_headers(client, module_login):
    return module_login(client, 'operator')


@pytest.fixture(scope='module')
def generated(client, faculty_headers):
    """Generate once (read-only) and share the result across tests here."""
    response = client.post(
        '/schedules/generate',
        headers=faculty_headers,
        json={'institution_id': 1, 'campus_id': 1, 'time_limit_seconds': 5.0},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_generate_creates_proposal_with_metrics(client, faculty_headers, generated):
    assert generated['status'] in ('OPTIMAL', 'FEASIBLE', 'INFEASIBLE')
    assert set(generated['metrics']) >= {
        'solver_status', 'solution_source', 'hard_constraint_violations',
        'soft_preference_matches', 'undesirable_slots', 'time_to_generate_ms',
    }
    assert generated['metrics']['hard_constraint_violations'] == 0
    assert generated['proposal_id'] > 0
    assert len(generated['schedule']) >= 3  # the three seeded Northbridge sessions


def test_generate_does_not_mutate_bookings(client, faculty_headers, admin_headers, generated):
    timetable = client.get('/institutions/1/timetable', headers=admin_headers).json()
    slots = {(row['day'], row['start_minute']) for row in timetable['sessions']}
    assert (0, 540) in slots  # seeded CS101 session, unchanged until approval


def test_proposals_are_listed_for_schedule_managers(client, faculty_headers, generated):
    proposals = client.get('/proposals', headers=faculty_headers)
    assert proposals.status_code == 200
    ids = [p['id'] for p in proposals.json()]
    assert generated['proposal_id'] in ids

    listing = next(p for p in proposals.json() if p['id'] == generated['proposal_id'])
    assert 'metrics' in listing
    assert listing['approved'] is False


def test_student_cannot_generate(client, student_headers):
    response = client.post(
        '/schedules/generate', headers=student_headers,
        json={'institution_id': 1, 'campus_id': 1},
    )
    assert response.status_code == 403


def test_operator_can_approve_and_publish(client, operator_headers, generated):
    approved = client.post(f"/proposals/{generated['proposal_id']}/approve", headers=operator_headers)
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body['approved'] is True
    assert body['updated_sessions'] >= 3

    # Every booking touched by the proposal is now published.
    proposals = client.get('/proposals', headers=operator_headers).json()
    listing = next(p for p in proposals if p['id'] == generated['proposal_id'])
    assert listing['approved'] is True

    # A second approval of the same proposal is refused.
    again = client.post(f"/proposals/{generated['proposal_id']}/approve", headers=operator_headers)
    assert again.status_code == 409


def test_audit_trail_records_generation_and_approval(client, admin_headers, generated):
    events = client.get('/audit-events', headers=admin_headers)
    assert events.status_code == 200
    kinds = {event['event_type'] for event in events.json()}
    assert 'schedule_generated' in kinds
    assert 'proposal_approved' in kinds


def test_cross_tenant_proposal_refused(client):
    harbor_login = client.post('/auth/login', json={'username': 'harbor-admin', 'password': 'demo-admin-harbor'})
    harbor_headers = {'Authorization': f"Bearer {harbor_login.json()['access_token']}"}
    listing = client.get('/proposals', headers=harbor_headers)
    assert listing.status_code == 200
    assert all(p['id'] != 1 for p in listing.json())
    refused = client.post('/proposals/1/approve', headers=harbor_headers)
    assert refused.status_code == 403
