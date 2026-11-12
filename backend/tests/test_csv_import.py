"""S-07 CSV import: valid files, all-or-nothing rejection with every row
reported, role gating, and cross-tenant refusal."""

from __future__ import annotations

import pytest
from app.core.db import engine
from app.models import Course, Lecturer, Room, StudentGroup
from fastapi.testclient import TestClient
from sqlmodel import Session, delete

VALID_ROOMS = (
    'campus_id,name,capacity,room_type,equipment\n'
    '1,CSV-ROOM-A,60,lecture,projector\n'
    '1,CSV-ROOM-B,24,lab,\n'
)

VALID_COURSES = (
    'code,name,required_room_type\n'
    'CSV101,CSV Intro to Testing,any\n'
    'CSV201,CSV Lab Methods,lab\n'
)


def _post_csv(client: TestClient, headers: dict, url: str, content: str, name: str = 'upload.csv'):
    return client.post(url, headers=headers, files={'file': (name, content, 'text/csv')})


def _room_names(client: TestClient, headers: dict) -> set[str]:
    response = client.get('/institutions/1/rooms', headers=headers)
    assert response.status_code == 200, response.text
    return {room['name'] for room in response.json()}


@pytest.fixture(scope='module', autouse=True)
def _remove_imported_rows():
    """Delete every row this module imports, whatever the outcome.

    The suite shares one database and other modules assert the exact seeded
    counts (e.g. 4 Northbridge rooms), so imported rows must not leak past
    this module. Runs even after a failing test because the fixture body
    before ``yield`` schedules teardown regardless.
    """
    yield
    with Session(engine) as session:
        session.exec(delete(Room).where(Room.name.startswith('CSV-ROOM')))
        session.exec(delete(Course).where(Course.code.startswith('CSV')))
        session.exec(delete(Lecturer).where(Lecturer.email.startswith('csv-')))
        session.exec(delete(StudentGroup).where(StudentGroup.name.startswith('CSV-GRP')))
        session.commit()


def test_valid_rooms_file_imports_every_row(client: TestClient, admin_headers: dict):
    before = _room_names(client, admin_headers)
    assert 'CSV-ROOM-A' not in before

    response = _post_csv(client, admin_headers, '/institutions/1/import/rooms', VALID_ROOMS)

    assert response.status_code == 201, response.text
    assert response.json() == {'dataset': 'rooms', 'imported': 2, 'errors': []}
    names = _room_names(client, admin_headers)
    assert {'CSV-ROOM-A', 'CSV-ROOM-B'} <= names

    # The import is part of the audit trail.
    events = client.get('/audit-events', headers=admin_headers).json()
    imports = [event for event in events if event['event_type'] == 'csv_import']
    assert any('2 row(s) imported' in event['message'] for event in imports)


def test_valid_courses_file_imports_every_row(client: TestClient, admin_headers: dict):
    response = _post_csv(client, admin_headers, '/institutions/1/import/courses', VALID_COURSES)

    assert response.status_code == 201, response.text
    assert response.json()['imported'] == 2
    courses = client.get('/institutions/1/courses', headers=admin_headers).json()
    codes = {course['code'] for course in courses}
    assert {'CSV101', 'CSV201'} <= codes


def test_bad_rows_report_every_error_and_import_nothing(client: TestClient, admin_headers: dict):
    """The core all-or-nothing contract: one pass reports every bad row and
    the database is left untouched."""
    before = _room_names(client, admin_headers)
    bad_file = (
        'campus_id,name,capacity\n'
        '1,CSV-ROOM-OK,50\n'  # row 2: valid
        '1,CSV-ROOM-BAD,abc\n'  # row 3: capacity not an integer
        '99,CSV-ROOM-FORG,60\n'  # row 4: campus of another tenant / nonexistent
        '1,,40\n'  # row 5: missing name
    )

    response = _post_csv(client, admin_headers, '/institutions/1/import/rooms', bad_file)

    assert response.status_code == 400, response.text
    detail = response.json()['detail']
    assert 'nothing was imported' in detail['message']
    # Every failing row is reported, with its file row number and a reason.
    reported = {error['row']: error['reason'] for error in detail['errors']}
    assert set(reported) == {3, 4, 5}
    assert 'not an integer' in reported[3]
    assert 'does not belong to this institution' in reported[4]
    assert 'name is required' in reported[5]
    # All-or-nothing: not even the valid row 2 was written.
    assert _room_names(client, admin_headers) == before
    assert 'CSV-ROOM-OK' not in before


def test_duplicate_inside_file_is_a_row_error(client: TestClient, admin_headers: dict):
    before = _room_names(client, admin_headers)
    duplicates = (
        'campus_id,name,capacity\n'
        '1,CSV-ROOM-DUP,40\n'
        '1,CSV-ROOM-DUP,50\n'
    )

    response = _post_csv(client, admin_headers, '/institutions/1/import/rooms', duplicates)

    assert response.status_code == 400, response.text
    errors = response.json()['detail']['errors']
    assert [error['row'] for error in errors] == [3]
    assert 'already exists' in errors[0]['reason']
    assert _room_names(client, admin_headers) == before


def test_missing_required_column_is_reported_against_the_header(client: TestClient, admin_headers: dict):
    response = _post_csv(client, admin_headers, '/institutions/1/import/rooms', 'campus_id,name\n1,OnlyName\n')

    assert response.status_code == 400, response.text
    errors = response.json()['detail']['errors']
    assert errors == [{'row': 1, 'reason': 'missing required column(s): capacity'}]


def test_header_only_file_imports_nothing(client: TestClient, admin_headers: dict):
    response = _post_csv(client, admin_headers, '/institutions/1/import/rooms', 'campus_id,name,capacity\n')

    assert response.status_code == 400, response.text
    assert 'no data rows' in response.json()['detail']['errors'][0]['reason']


def test_lecturers_and_student_groups_import(client: TestClient, admin_headers: dict):
    lecturers = 'name,email\nCSV Lecturer,csv-lecturer@northbridge.edu\n'
    groups = 'name,size\nCSV-GRP-1,25\n'

    lecturers_response = _post_csv(client, admin_headers, '/institutions/1/import/lecturers', lecturers)
    groups_response = _post_csv(client, admin_headers, '/institutions/1/import/student-groups', groups)

    assert lecturers_response.status_code == 201, lecturers_response.text
    assert groups_response.status_code == 201, groups_response.text
    assert lecturers_response.json()['imported'] == 1
    assert groups_response.json()['imported'] == 1
    listed = client.get('/institutions/1/lecturers', headers=admin_headers).json()
    assert 'csv-lecturer@northbridge.edu' in {row['email'] for row in listed}


def test_invalid_email_is_a_row_error(client: TestClient, admin_headers: dict):
    response = _post_csv(
        client, admin_headers, '/institutions/1/import/lecturers',
        'name,email\nNobody,not-an-email\n',
    )

    assert response.status_code == 400, response.text
    errors = response.json()['detail']['errors']
    assert [error['row'] for error in errors] == [2]
    assert 'not a valid address' in errors[0]['reason']


def test_cross_tenant_import_is_rejected(client: TestClient, admin_headers: dict):
    """Harbor's administrator cannot post a file into Northbridge — and the
    target tenant's data is untouched."""
    login = client.post('/auth/login', json={'username': 'harbor-admin', 'password': 'demo-admin-harbor'})
    assert login.status_code == 200, login.text
    harbor_headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
    before = _room_names(client, admin_headers)

    read_response = client.get('/institutions/1/rooms', headers=harbor_headers)
    response = _post_csv(client, harbor_headers, '/institutions/1/import/rooms', VALID_ROOMS)

    assert read_response.status_code == 403  # cross-tenant reads are refused too
    assert response.status_code == 403
    assert response.json()['detail'] == 'tenant mismatch'
    assert _room_names(client, admin_headers) == before


def test_faculty_and_students_cannot_import(client: TestClient, module_login):
    faculty = module_login(client, 'faculty')
    student = module_login(client, 'student')
    for headers in (faculty, student):
        response = _post_csv(client, headers, '/institutions/1/import/rooms', VALID_ROOMS)
        assert response.status_code == 403, response.text
        assert 'role' in response.json()['detail']


def test_operator_can_import(client: TestClient, module_login):
    operator = module_login(client, 'operator')
    content = 'campus_id,name,capacity\n1,CSV-ROOM-OPS,35\n'
    response = _post_csv(client, operator, '/institutions/1/import/rooms', content)
    assert response.status_code == 201, response.text


def test_unauthenticated_import_is_rejected(client: TestClient):
    response = _post_csv(client, {}, '/institutions/1/import/rooms', VALID_ROOMS)
    assert response.status_code == 401


def test_unknown_dataset_is_rejected(client: TestClient, admin_headers: dict):
    response = _post_csv(client, admin_headers, '/institutions/1/import/lecterns', 'name\nX\n')
    assert response.status_code == 404
    assert 'supported:' in response.json()['detail']
