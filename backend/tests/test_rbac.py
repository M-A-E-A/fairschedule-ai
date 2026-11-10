"""Role-based access control: every privilege-escalation path is rejected by
the backend, not merely hidden in the interface."""

from fastapi.testclient import TestClient


def test_student_cannot_generate_schedule(client: TestClient, student_headers: dict[str, str]):
    response = client.post(
        '/schedules/generate', headers=student_headers, json={'institution_id': 1, 'campus_id': 1}
    )
    assert response.status_code == 403
    assert 'student' in response.json()['detail']


def test_student_cannot_create_rooms(client: TestClient, student_headers: dict[str, str]):
    response = client.post(
        '/institutions/1/rooms',
        headers=student_headers,
        json={'campus_id': 1, 'name': 'X999', 'capacity': 10, 'room_type': 'lecture'},
    )
    assert response.status_code == 403


def test_student_cannot_update_rooms(client: TestClient, student_headers: dict[str, str]):
    response = client.patch('/rooms/1', headers=student_headers, json={'capacity': 1})
    assert response.status_code == 403


def test_student_cannot_create_bookings(client: TestClient, student_headers: dict[str, str]):
    response = client.post(
        '/institutions/1/bookings',
        headers=student_headers,
        json={
            'campus_id': 1,
            'course_id': 1,
            'lecturer_id': 1,
            'student_group_id': 1,
            'room_id': 1,
            'day': 4,
            'start_minute': 600,
            'duration_minute': 60,
        },
    )
    assert response.status_code == 403


def test_student_cannot_manage_users(client: TestClient, student_headers: dict[str, str]):
    assert client.get('/admin/users', headers=student_headers).status_code == 403
    response = client.post(
        '/admin/users',
        headers=student_headers,
        json={
            'username': 'evil',
            'email': 'evil@example.com',
            'full_name': 'Evil',
            'role': 'administrator',
            'password': 'password123',
        },
    )
    assert response.status_code == 403


def test_student_cannot_read_audit_log(client: TestClient, student_headers: dict[str, str]):
    assert client.get('/audit-events', headers=student_headers).status_code == 403


def test_student_cannot_approve_proposals(client: TestClient, student_headers: dict[str, str]):
    response = client.post('/proposals/1/approve', headers=student_headers)
    assert response.status_code == 403


def test_faculty_cannot_approve_proposals(client: TestClient, faculty_headers: dict[str, str]):
    response = client.post('/proposals/1/approve', headers=faculty_headers)
    assert response.status_code == 403


def test_operator_cannot_manage_users(client: TestClient, operator_headers: dict[str, str]):
    assert client.get('/admin/users', headers=operator_headers).status_code == 403


def test_operator_cannot_read_audit_log(client: TestClient, operator_headers: dict[str, str]):
    assert client.get('/audit-events', headers=operator_headers).status_code == 403


def test_faculty_can_generate_schedule(client: TestClient, faculty_headers: dict[str, str]):
    """Faculty/schedulers are a scheduling role and must be able to generate."""
    response = client.post(
        '/schedules/generate', headers=faculty_headers, json={'institution_id': 1, 'campus_id': 1}
    )
    assert response.status_code == 200


def test_student_can_ask_the_ai(client: TestClient, student_headers: dict[str, str]):
    """Students may query the assistant; it answers with their own data only."""
    response = client.post('/ai/chat', headers=student_headers, json={'prompt': 'When is my next class?'})
    assert response.status_code == 200


def test_requests_without_token_are_rejected_everywhere(client: TestClient):
    for method, path in (
        ('get', '/dashboard/overview'),
        ('get', '/me/schedule'),
        ('get', '/institutions/1/rooms'),
        ('get', '/admin/users'),
        ('post', '/schedules/generate'),
        ('post', '/ai/chat'),
    ):
        response = getattr(client, method)(path, json={} if method == 'post' else None)
        assert response.status_code == 401, f'{method.upper()} {path} -> {response.status_code}'
