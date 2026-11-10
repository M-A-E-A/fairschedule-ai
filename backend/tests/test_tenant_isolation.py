"""Tenant isolation: cross-tenant reads and writes are refused by the backend
even when the attacker holds a valid token and can guess resource ids."""

from fastapi.testclient import TestClient


def test_tenant_summary_requires_auth(client: TestClient):
    assert client.get('/demo/tenant-summary').status_code == 401


def test_tenant_summary_requires_administrator(client: TestClient, student_headers: dict[str, str]):
    assert client.get('/demo/tenant-summary', headers=student_headers).status_code == 403


def test_tenant_summary_shows_only_own_tenant(client: TestClient, admin_headers, harbor_admin_headers):
    north = client.get('/demo/tenant-summary', headers=admin_headers)
    assert north.status_code == 200
    institutions = north.json()['institutions']
    assert len(institutions) == 1
    assert institutions[0]['id'] == 1
    assert institutions[0]['name'] == 'Northbridge University'

    harbor = client.get('/demo/tenant-summary', headers=harbor_admin_headers)
    assert harbor.status_code == 200
    institutions = harbor.json()['institutions']
    assert len(institutions) == 1
    assert institutions[0]['id'] == 2
    assert institutions[0]['name'] == 'Harbor College'


def test_admin_user_list_is_tenant_scoped(client: TestClient, admin_headers):
    response = client.get('/admin/users', headers=admin_headers)
    assert response.status_code == 200
    usernames = {user['username'] for user in response.json()}
    assert 'harbor-admin' not in usernames
    assert {'admin', 'operator', 'faculty', 'student'} <= usernames


def test_cross_tenant_user_mutation_rejected(client: TestClient, admin_headers, harbor_admin_headers):
    harbor_users = client.get('/admin/users', headers=harbor_admin_headers).json()
    harbor_admin_id = next(user['id'] for user in harbor_users if user['username'] == 'harbor-admin')

    assert (
        client.patch(
            f'/admin/users/{harbor_admin_id}', headers=admin_headers, json={'role': 'student'}
        ).status_code
        == 403
    )
    assert client.delete(f'/admin/users/{harbor_admin_id}', headers=admin_headers).status_code == 403
    # The other tenant's admin must be untouched.
    still = client.get('/admin/users', headers=harbor_admin_headers).json()
    assert next(user for user in still if user['id'] == harbor_admin_id)['role'] == 'administrator'


def test_cross_tenant_room_mutation_rejected(client: TestClient, admin_headers, harbor_admin_headers):
    harbor_rooms = client.get('/institutions/2/rooms', headers=harbor_admin_headers).json()
    harbor_room_id = next(room['id'] for room in harbor_rooms if room['name'] == 'H1')

    response = client.patch(f'/rooms/{harbor_room_id}', headers=admin_headers, json={'capacity': 1})
    assert response.status_code == 403
    assert response.json()['detail'] == 'tenant mismatch'

    assert client.delete(f'/rooms/{harbor_room_id}', headers=admin_headers).status_code == 403

    still = client.get('/institutions/2/rooms', headers=harbor_admin_headers).json()
    assert next(room for room in still if room['id'] == harbor_room_id)['capacity'] == 70


def test_booking_cannot_reference_another_tenants_room(client: TestClient, admin_headers, harbor_admin_headers):
    harbor_rooms = client.get('/institutions/2/rooms', headers=harbor_admin_headers).json()
    harbor_room_id = next(room['id'] for room in harbor_rooms if room['name'] == 'H1')
    response = client.post(
        '/institutions/1/bookings',
        headers=admin_headers,
        json={
            'campus_id': 1,
            'course_id': 1,
            'lecturer_id': 1,
            'student_group_id': 1,
            'room_id': harbor_room_id,
            'day': 4,
            'start_minute': 720,
            'duration_minute': 60,
        },
    )
    assert response.status_code == 403
    assert 'another institution' in response.json()['detail']


def test_cross_tenant_campus_and_resource_reads_rejected(client: TestClient, operator_headers, student_headers):
    assert client.get('/institutions/2/campuses', headers=operator_headers).status_code == 403
    assert client.get('/institutions/2/bookings', headers=student_headers).status_code == 403
    assert client.get('/institutions/2/courses', headers=operator_headers).status_code == 403
    assert client.get('/institutions/2/timetable', headers=operator_headers).status_code == 403


def test_cross_tenant_proposal_approval_rejected(client: TestClient, admin_headers, harbor_admin_headers):
    generated = client.post(
        '/schedules/generate', headers=admin_headers, json={'institution_id': 1, 'campus_id': 1}
    )
    assert generated.status_code == 200
    proposal_id = generated.json()['proposal_id']

    response = client.post(f'/proposals/{proposal_id}/approve', headers=harbor_admin_headers)
    assert response.status_code == 403

    # ...and the proposal must still be unapproved for its own tenant.
    own = client.get('/proposals', headers=admin_headers).json()
    assert next(p for p in own if p['id'] == proposal_id)['approved'] is False


def test_schedules_generate_cannot_target_other_tenant(client: TestClient, admin_headers):
    response = client.post(
        '/schedules/generate', headers=admin_headers, json={'institution_id': 2, 'campus_id': 3}
    )
    assert response.status_code == 403
    assert response.json()['detail'] == 'tenant mismatch'


def test_student_bookings_only_show_own_group(client: TestClient, student_headers):
    response = client.get('/institutions/1/bookings', headers=student_headers)
    assert response.status_code == 200
    rows = response.json()
    assert rows, 'seeded student cohort must have sessions'
    assert {row['student_group_id'] for row in rows} == {1}
