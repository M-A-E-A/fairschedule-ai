"""Dashboard, role-scoped schedules, and the read-only AI assistant."""

from __future__ import annotations

import pytest

DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']


@pytest.fixture(scope='module')
def student_headers(client, module_login):
    return module_login(client, 'student')


@pytest.fixture(scope='module')
def faculty_headers(client, module_login):
    return module_login(client, 'faculty')


@pytest.fixture(scope='module')
def operator_headers(client, module_login):
    return module_login(client, 'operator')


def test_overview_is_scoped_to_own_tenant(client, admin_headers, module_login):
    north = client.get('/dashboard/overview', headers=admin_headers).json()
    assert north['institution_id'] == 1
    assert north['institution_name'] == 'Northbridge University'
    assert north['role'] == 'administrator'
    assert north['campuses'] == 2
    assert north['rooms'] == 4  # A101, B204, C315, T12
    assert north['courses'] == 3
    assert north['sessions'] == 3

    harbor_headers = module_login(client, 'harbor-admin', 'demo-admin-harbor')
    harbor = client.get('/dashboard/overview', headers=harbor_headers).json()
    assert harbor['institution_id'] == 2
    assert harbor['institution_name'] == 'Harbor College'
    assert harbor['rooms'] == 1
    assert harbor['sessions'] == 1
    # The Harbor dashboard never mentions Northbridge data.
    assert 'Northbridge' not in str(harbor)


def test_overview_for_all_roles(client, admin_headers, student_headers, faculty_headers, operator_headers):
    for headers in (student_headers, faculty_headers, operator_headers, admin_headers):
        response = client.get('/dashboard/overview', headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body['institution_id'] == 1
        assert set(body) >= {'rooms', 'courses', 'lecturers', 'student_groups', 'sessions', 'published_sessions'}


def test_student_me_schedule_is_group_scoped(client, student_headers):
    response = client.get('/me/schedule', headers=student_headers)
    assert response.status_code == 200
    body = response.json()
    assert body['scope'] == 'student'
    assert len(body['sessions']) >= 2
    # CS Year 1 has CS101 (A101) and MTH120 (C315), never the DBS201 session
    # that belongs to CS Year 2.
    course_codes = {session['course_code'] for session in body['sessions']}
    assert course_codes == {'CS101', 'MTH120'}
    assert all(session['student_group_id'] == 1 for session in body['sessions'])


def test_faculty_me_schedule_is_lecturer_scoped(client, faculty_headers):
    body = client.get('/me/schedule', headers=faculty_headers).json()
    assert body['scope'] == 'lecturer'
    assert len(body['sessions']) == 1
    assert body['sessions'][0]['course_code'] == 'CS101'


def test_operator_me_schedule_is_institution_scoped(client, operator_headers):
    body = client.get('/me/schedule', headers=operator_headers).json()
    assert body['scope'] == 'institution'
    assert len(body['sessions']) == 3


def test_student_cannot_read_institution_timetable(client, student_headers):
    response = client.get('/institutions/1/timetable', headers=student_headers)
    assert response.status_code == 403


def test_staff_can_read_institution_timetable(client, operator_headers):
    response = client.get('/institutions/1/timetable', headers=operator_headers)
    assert response.status_code == 200
    body = response.json()
    assert body['institution_id'] == 1
    assert len(body['sessions']) == 3
    assert all(DAY_NAMES[session['day']] == session['day_name'] for session in body['sessions'])


def test_campuses_are_listed_per_tenant(client, admin_headers, module_login):
    campuses = client.get('/institutions/1/campuses', headers=admin_headers).json()
    assert len(campuses) == 2
    by_slug = {campus['slug']: campus for campus in campuses}
    assert by_slug['main']['room_count'] == 3  # A101, B204, C315
    assert by_slug['tech-park']['room_count'] == 1  # T12

    harbor_campuses = client.get(
        '/institutions/2/campuses', headers=module_login(client, 'harbor-admin', 'demo-admin-harbor')
    ).json()
    assert len(harbor_campuses) == 1
    assert harbor_campuses[0]['slug'] == 'harbor-south'


def test_student_ai_answer_is_scoped_to_own_cohort(client, student_headers):
    response = client.post('/ai/chat', headers=student_headers, json={'prompt': 'What is my schedule today?'})
    assert response.status_code == 200
    answer = response.json()['answer']
    assert 'AI is not configured' in answer
    # Only the student's own cohort's sessions are mentioned.
    assert 'CS101' in answer
    assert 'MTH120' in answer
    assert 'DBS201' not in answer
    assert 'Harbor' not in answer
    # The assistant refuses to mutate schedules.
    assert 'generate a schedule proposal' in answer


def test_faculty_ai_answer_is_teaching_scoped(client, faculty_headers):
    answer = client.post('/ai/chat', headers=faculty_headers, json={'prompt': 'What do I teach?'}).json()['answer']
    assert 'CS101' in answer
    assert 'DBS201' not in answer  # Sam Chen's session


def test_admin_ai_answer_is_institution_scoped(client, admin_headers):
    answer = client.post(
        '/ai/chat', headers=admin_headers, json={'prompt': 'Summarise the institution.'}
    ).json()['answer']
    assert 'Northbridge' in answer
    assert 'Harbor' not in answer
    assert 'AI is not configured' in answer


def test_ai_rejects_empty_prompt(client, admin_headers):
    response = client.post('/ai/chat', headers=admin_headers, json={'prompt': '   '})
    assert response.status_code == 400


def test_ai_requires_authentication(client):
    response = client.post('/ai/chat', json={'prompt': 'hello'})
    assert response.status_code == 401
