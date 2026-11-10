"""Room and booking management for campus operators/faculty, including
write-time enforcement of the hard constraints."""

from fastapi.testclient import TestClient


def _ids(client: TestClient, headers: dict[str, str]) -> dict:
    rooms = {room['name']: room['id'] for room in client.get('/institutions/1/rooms', headers=headers).json()}
    courses = {c['code']: c['id'] for c in client.get('/institutions/1/courses', headers=headers).json()}
    lecturers = {row['name']: row['id'] for row in client.get('/institutions/1/lecturers', headers=headers).json()}
    groups = {g['name']: g['id'] for g in client.get('/institutions/1/student-groups', headers=headers).json()}
    campuses = {c['slug']: c['id'] for c in client.get('/institutions/1/campuses', headers=headers).json()}
    return {'rooms': rooms, 'courses': courses, 'lecturers': lecturers, 'groups': groups, 'campuses': campuses}


def test_room_crud_lifecycle(client: TestClient, operator_headers):
    created = client.post(
        '/institutions/1/rooms',
        headers=operator_headers,
        json={'campus_id': 1, 'name': 'R-NEW', 'capacity': 55, 'room_type': 'seminar', 'equipment': 'board'},
    )
    assert created.status_code == 201, created.text
    room_id = created.json()['id']
    assert created.json()['capacity'] == 55

    updated = client.patch(f'/rooms/{room_id}', headers=operator_headers, json={'capacity': 60})
    assert updated.status_code == 200
    assert updated.json()['capacity'] == 60

    listing = client.get('/institutions/1/rooms', headers=operator_headers).json()
    assert room_id in {room['id'] for room in listing}

    deleted = client.delete(f'/rooms/{room_id}', headers=operator_headers)
    assert deleted.status_code == 204
    listing = client.get('/institutions/1/rooms', headers=operator_headers).json()
    assert room_id not in {room['id'] for room in listing}


def test_room_create_rejects_foreign_campus(client: TestClient, admin_headers, harbor_admin_headers):
    harbor_campuses = client.get('/institutions/2/campuses', headers=harbor_admin_headers).json()
    foreign_campus_id = harbor_campuses[0]['id']
    response = client.post(
        '/institutions/1/rooms',
        headers=admin_headers,
        json={'campus_id': foreign_campus_id, 'name': 'SNEAK', 'capacity': 10},
    )
    assert response.status_code == 403


def test_faculty_can_create_bookings_and_students_cannot(
    client: TestClient, faculty_headers, student_headers, admin_headers
):
    ids = _ids(client, admin_headers)
    payload = {
        'campus_id': ids['campuses']['main'],
        'course_id': ids['courses']['MTH120'],
        'lecturer_id': ids['lecturers']['Priya Nair'],
        'student_group_id': ids['groups']['CS Year 1'],
        'room_id': ids['rooms']['C315'],
        'day': 3,
        'start_minute': 660,
        'duration_minute': 90,
    }
    created = client.post('/institutions/1/bookings', headers=faculty_headers, json=payload)
    assert created.status_code == 201, created.text
    booking_id = created.json()['id']

    # Same cohort, overlapping time in another main-campus room -> clash.
    # A101 is on the main campus (T12 is on Tech Park), seats the cohort and
    # satisfies the room type, so the write reaches the conflict check.
    clash = dict(payload, room_id=ids['rooms']['A101'], start_minute=720)
    conflict = client.post('/institutions/1/bookings', headers=faculty_headers, json=clash)
    assert conflict.status_code == 409
    assert 'student_group' in conflict.json()['detail']

    # Students can never create bookings.
    denied = client.post('/institutions/1/bookings', headers=student_headers, json=payload)
    assert denied.status_code == 403

    # Faculty may remove their own booking again.
    assert client.delete(f'/bookings/{booking_id}', headers=faculty_headers).status_code == 204


def test_booking_rejects_room_overlap(client: TestClient, faculty_headers, admin_headers):
    ids = _ids(client, admin_headers)
    existing = client.get('/institutions/1/bookings', headers=admin_headers).json()
    first = next(b for b in existing if b['day'] == 0 and b['start_minute'] == 540)
    response = client.post(
        '/institutions/1/bookings',
        headers=faculty_headers,
        json={
            'campus_id': first['campus_id'],
            'course_id': ids['courses']['CS101'],
            'lecturer_id': ids['lecturers']['Sam Chen'],
            'student_group_id': ids['groups']['CS Year 2'],
            'room_id': first['room_id'],
            'day': 0,
            'start_minute': 540,
            'duration_minute': 60,
        },
    )
    assert response.status_code == 409
    assert 'room' in response.json()['detail']


def test_booking_rejects_lecturer_conflict(client: TestClient, faculty_headers, admin_headers):
    ids = _ids(client, admin_headers)
    response = client.post(
        '/institutions/1/bookings',
        headers=faculty_headers,
        json={
            'campus_id': ids['campuses']['main'],
            'course_id': ids['courses']['CS101'],
            # Ada Reed already teaches CS101 on Monday 09:00 in a different room.
            'lecturer_id': ids['lecturers']['Ada Reed'],
            'student_group_id': ids['groups']['CS Year 2'],
            'room_id': ids['rooms']['C315'],
            'day': 0,
            'start_minute': 570,
            'duration_minute': 60,
        },
    )
    assert response.status_code == 409
    assert 'lecturer' in response.json()['detail']


def test_booking_rejects_capacity_violation(client: TestClient, faculty_headers, admin_headers):
    ids = _ids(client, admin_headers)
    small = client.post(
        '/institutions/1/rooms',
        headers=admin_headers,
        json={'campus_id': ids['campuses']['main'], 'name': 'TINY', 'capacity': 10, 'room_type': 'lecture'},
    )
    tiny_id = small.json()['id']
    response = client.post(
        '/institutions/1/bookings',
        headers=faculty_headers,
        json={
            'campus_id': ids['campuses']['main'],
            'course_id': ids['courses']['CS101'],
            'lecturer_id': ids['lecturers']['Sam Chen'],
            'student_group_id': ids['groups']['CS Year 1'],  # 35 students
            'room_id': tiny_id,
            'day': 4,
            'start_minute': 540,
            'duration_minute': 60,
        },
    )
    assert response.status_code == 409
    assert 'capacity' in response.json()['detail']
    # Clean up so later runs are unaffected.
    assert client.delete(f'/rooms/{tiny_id}', headers=admin_headers).status_code == 204


def test_booking_rejects_room_type_mismatch(client: TestClient, faculty_headers, admin_headers):
    ids = _ids(client, admin_headers)
    response = client.post(
        '/institutions/1/bookings',
        headers=faculty_headers,
        json={
            'campus_id': ids['campuses']['main'],
            'course_id': ids['courses']['DBS201'],  # requires a lab
            'lecturer_id': ids['lecturers']['Sam Chen'],
            'student_group_id': ids['groups']['CS Year 2'],
            'room_id': ids['rooms']['A101'],  # lecture hall
            'day': 4,
            'start_minute': 840,
            'duration_minute': 60,
        },
    )
    assert response.status_code == 409
    assert 'room type' in response.json()['detail']


def test_booking_update_and_delete(client: TestClient, faculty_headers, admin_headers):
    ids = _ids(client, admin_headers)
    created = client.post(
        '/institutions/1/bookings',
        headers=faculty_headers,
        json={
            'campus_id': ids['campuses']['main'],
            'course_id': ids['courses']['CS101'],
            'lecturer_id': ids['lecturers']['Ada Reed'],
            'student_group_id': ids['groups']['CS Year 2'],
            'room_id': ids['rooms']['A101'],
            'day': 4,
            'start_minute': 540,
            'duration_minute': 90,
        },
    )
    assert created.status_code == 201, created.text
    booking_id = created.json()['id']

    updated = client.patch(f'/bookings/{booking_id}', headers=faculty_headers, json={'start_minute': 660})
    assert updated.status_code == 200
    assert updated.json()['start_minute'] == 660

    # Moving onto a slot a seeded booking already occupies (Monday 09:00 in
    # A101, Ada Reed) must be refused by re-validation.
    clash = client.patch(f'/bookings/{booking_id}', headers=faculty_headers, json={'day': 0, 'start_minute': 540})
    assert clash.status_code == 409

    assert client.delete(f'/bookings/{booking_id}', headers=faculty_headers).status_code == 204
    assert client.patch(f'/bookings/{booking_id}', headers=faculty_headers, json={'day': 1}).status_code == 404


def test_room_delete_blocked_while_booked(client: TestClient, admin_headers):
    rooms = client.get('/institutions/1/rooms', headers=admin_headers).json()
    booked_room_id = next(
        b['room_id'] for b in client.get('/institutions/1/bookings', headers=admin_headers).json()
    )
    assert any(room['id'] == booked_room_id for room in rooms)
    response = client.delete(f'/rooms/{booked_room_id}', headers=admin_headers)
    assert response.status_code == 409
