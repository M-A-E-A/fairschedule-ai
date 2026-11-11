"""S-06: timetable publish lifecycle — versioning, diff, RBAC, audit events.

Publishing freezes the tenant's current bookings as a named, immutable
version; the diff compares the live draft against the latest published
version. These tests exercise publish, version listing, diff correctness
(including the empty-diff and never-published cases), RBAC, tenant scoping,
and the audit trail.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _ids(client: TestClient, headers: dict[str, str]) -> dict:
    rooms = {room['name']: room['id'] for room in client.get('/institutions/1/rooms', headers=headers).json()}
    courses = {c['code']: c['id'] for c in client.get('/institutions/1/courses', headers=headers).json()}
    lecturers = {row['name']: row['id'] for row in client.get('/institutions/1/lecturers', headers=headers).json()}
    groups = {g['name']: g['id'] for g in client.get('/institutions/1/student-groups', headers=headers).json()}
    campuses = {c['slug']: c['id'] for c in client.get('/institutions/1/campuses', headers=headers).json()}
    return {'rooms': rooms, 'courses': courses, 'lecturers': lecturers, 'groups': groups, 'campuses': campuses}


def test_publish_freezes_named_version_with_audit(client, operator_headers, admin_headers):
    before = client.get('/institutions/1/bookings', headers=admin_headers).json()
    published = client.post(
        '/institutions/1/timetable/publish', headers=operator_headers, json={'label': 'Smoke v1'}
    )
    assert published.status_code == 200, published.text
    body = published.json()
    version_number = body['version']
    assert body['version'] >= 1
    assert body['label'] == 'Smoke v1'
    assert body['published_by_email'] == 'operator@northbridge.edu'
    assert body['session_count'] == len(before)
    assert body['published_at']

    versions = client.get('/institutions/1/timetable/versions', headers=admin_headers).json()
    assert versions[0]['version'] == body['version']  # newest first
    entry = next(v for v in versions if v['version'] == body['version'])
    assert entry['label'] == 'Smoke v1'
    assert entry['session_count'] == len(before)

    # Publishing is part of the audit trail.
    events = client.get('/audit-events', headers=admin_headers).json()
    matching = [event for event in events if event['event_type'] == 'timetable_published']
    assert any(
        f'version {version_number}' in event['message'] and 'Smoke v1' in event['message']
        for event in matching
    )


def test_publish_assigns_default_label_when_blank(client, operator_headers):
    published = client.post('/institutions/1/timetable/publish', headers=operator_headers, json={})
    assert published.status_code == 200, published.text
    body = published.json()
    assert body['label'] == f'Version {body["version"]}'


def test_versions_and_diff_are_staff_only(client, faculty_headers, student_headers):
    assert client.get('/institutions/1/timetable/versions', headers=faculty_headers).status_code == 200
    assert client.get('/institutions/1/timetable/diff', headers=faculty_headers).status_code == 200
    assert client.get('/institutions/1/timetable/versions', headers=student_headers).status_code == 403
    assert client.get('/institutions/1/timetable/diff', headers=student_headers).status_code == 403


def test_only_approvers_may_publish(client, faculty_headers, student_headers):
    response = client.post('/institutions/1/timetable/publish', headers=faculty_headers, json={})
    assert response.status_code == 403
    response = client.post('/institutions/1/timetable/publish', headers=student_headers, json={})
    assert response.status_code == 403


def test_publish_is_tenant_scoped(client, harbor_admin_headers):
    response = client.post('/institutions/1/timetable/publish', headers=harbor_admin_headers, json={})
    assert response.status_code == 403
    # The other tenant's version list never contains institution 1's labels.
    theirs = client.get('/institutions/2/timetable/versions', headers=harbor_admin_headers).json()
    assert all(entry['label'] != 'Smoke v1' for entry in theirs)


def test_diff_empty_right_after_publish(client, admin_headers):
    published = client.post(
        '/institutions/1/timetable/publish', headers=admin_headers, json={'label': 'Diff baseline'}
    )
    assert published.status_code == 200, published.text
    diff = client.get('/institutions/1/timetable/diff', headers=admin_headers).json()
    current = client.get('/institutions/1/bookings', headers=admin_headers).json()
    assert diff['published_version'] == published.json()['version']
    assert diff['draft_session_count'] == len(current)
    assert diff['added'] == []
    assert diff['removed'] == []
    assert diff['moved'] == []


def test_diff_reports_added_moved_removed_and_restores(client, admin_headers, operator_headers):
    ids = _ids(client, admin_headers)
    # Sunday 20:00 clashes with nothing seeded or test-created.
    payload = {
        'campus_id': ids['campuses']['main'],
        'course_id': ids['courses']['MTH120'],
        'lecturer_id': ids['lecturers']['Sam Chen'],
        'student_group_id': ids['groups']['CS Year 2'],
        'room_id': ids['rooms']['A101'],
        'day': 6,
        'start_minute': 1200,
        'duration_minute': 60,
    }

    # A booking that exists *before* the publish, so moving it later is a
    # "moved" session rather than an "added" one.
    created = client.post('/institutions/1/bookings', headers=operator_headers, json=payload)
    assert created.status_code == 201, created.text
    moved_id = created.json()['id']

    published = client.post(
        '/institutions/1/timetable/publish', headers=operator_headers, json={'label': 'Diff fixture'}
    )
    assert published.status_code == 200, published.text
    base = client.get('/institutions/1/timetable/diff', headers=admin_headers).json()
    assert base['added'] == [] and base['moved'] == [] and base['removed'] == []

    # Added: booked after the publish (Saturday, so it can never clash with
    # the Sunday booking being moved below).
    extra = client.post(
        '/institutions/1/bookings',
        headers=operator_headers,
        json=dict(payload, day=5, start_minute=1200),
    )
    assert extra.status_code == 201, extra.text
    added_id = extra.json()['id']
    diff = client.get('/institutions/1/timetable/diff', headers=admin_headers).json()
    assert [row['id'] for row in diff['added']] == [added_id]
    assert diff['moved'] == [] and diff['removed'] == []

    # Moved: the pre-publish booking changes its start time.
    patched = client.patch(
        f'/bookings/{moved_id}', headers=operator_headers, json={'start_minute': 1260}
    )
    assert patched.status_code == 200, patched.text
    diff = client.get('/institutions/1/timetable/diff', headers=admin_headers).json()
    assert [row['id'] for row in diff['added']] == [added_id]
    assert len(diff['moved']) == 1
    change = diff['moved'][0]
    assert change['id'] == moved_id
    assert change['from']['start_minute'] == 1200
    assert change['to']['start_minute'] == 1260
    assert change['from']['day'] == change['to']['day'] == 6
    assert diff['removed'] == []

    # Removed: the pre-publish booking is deleted.
    assert client.delete(f'/bookings/{moved_id}', headers=operator_headers).status_code == 204
    diff = client.get('/institutions/1/timetable/diff', headers=admin_headers).json()
    assert [row['id'] for row in diff['added']] == [added_id]
    assert diff['moved'] == []
    assert [row['id'] for row in diff['removed']] == [moved_id]

    # Cleanup: both test bookings are gone. The Sunday booking the publish
    # snapshot contained correctly remains as 'removed' — deleting a session
    # the published version contains is a real change, not a restoration.
    assert client.delete(f'/bookings/{added_id}', headers=operator_headers).status_code == 204
    diff = client.get('/institutions/1/timetable/diff', headers=admin_headers).json()
    assert diff['added'] == [] and diff['moved'] == []
    assert [row['id'] for row in diff['removed']] == [moved_id]


def test_diff_before_any_publish_treats_whole_draft_as_added(client, harbor_admin_headers):
    """Harbor College is never published by these tests, so its diff is the
    honest "nothing published yet" shape rather than a fake comparison."""
    diff = client.get('/institutions/2/timetable/diff', headers=harbor_admin_headers).json()
    assert diff['published_version'] is None
    assert diff['published_label'] is None
    harbor_bookings = client.get('/institutions/2/bookings', headers=harbor_admin_headers).json()
    assert diff['draft_session_count'] == len(harbor_bookings)
    assert {row['id'] for row in diff['added']} == {row['id'] for row in harbor_bookings}
    assert diff['removed'] == [] and diff['moved'] == []
