"""Administrator-only user management: cross-tenant isolation, self-guards,
role changes and validation."""

from __future__ import annotations

import pytest


@pytest.fixture(scope='module')
def admin_headers(client, module_login):
    return module_login(client, 'admin')


def test_create_user_201_and_login(client, admin_headers):
    before = {u['id'] for u in client.get('/admin/users', headers=admin_headers).json()}
    created = client.post(
        '/admin/users',
        headers=admin_headers,
        json={
            'username': 'newlect',
            'email': 'newlect@northbridge.edu',
            'password': 'demo-newlect',
            'full_name': 'New Lecturer',
            'role': 'faculty',
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body['role'] == 'faculty'
    assert body['institution_id'] == 1
    after = {u['id'] for u in client.get('/admin/users', headers=admin_headers).json()}
    assert before | {body['id']} == after

    login = client.post('/auth/login', json={'username': 'newlect', 'password': 'demo-newlect'})
    assert login.status_code == 200
    assert login.json()['role'] == 'faculty'


def test_duplicate_username_and_email_rejected(client, admin_headers):
    dup = client.post(
        '/admin/users', headers=admin_headers,
        json={'username': 'admin', 'email': 'other@northbridge.edu', 'password': 'demo-sample', 'role': 'student'},
    )
    assert dup.status_code == 409

    # The existing seed email belongs to `admin`; a fresh username must not
    # allow the duplicate through.
    dup_email = client.post(
        '/admin/users', headers=admin_headers,
        json={'username': 'otheruser', 'email': 'admin@northbridge.edu', 'password': 'demo-sample', 'role': 'student'},
    )
    assert dup_email.status_code == 409


def test_invalid_role_rejected(client, admin_headers):
    created = client.post(
        '/admin/users', headers=admin_headers,
        json={'username': 'bogus', 'email': 'bogus@northbridge.edu', 'password': 'demo-sample', 'role': 'superuser'},
    )
    assert created.status_code == 422


def test_foreign_links_rejected(client, admin_headers):
    # Northbridge's administrator cannot attach Harbor's student group.
    foreign_group = client.post(
        '/admin/users', headers=admin_headers,
        json={
            'username': 'spy', 'email': 'spy@northbridge.edu', 'password': 'demo-sample', 'role': 'student',
            'student_group_id': 3,  # Engineering Cohort (institution 2)
        },
    )
    assert foreign_group.status_code == 403

    foreign_lecturer = client.post(
        '/admin/users', headers=admin_headers,
        json={
            'username': 'spy2', 'email': 'spy2@northbridge.edu', 'password': 'demo-sample', 'role': 'faculty',
            'lecturer_id': 4,  # Milo Stone (institution 2)
        },
    )
    assert foreign_lecturer.status_code == 403


def test_operator_cannot_manage_users(client, module_login):
    operator_headers = module_login(client, 'operator')
    listing = client.get('/admin/users', headers=operator_headers)
    assert listing.status_code == 403


def test_update_role_and_me_reflects_change(client, admin_headers, module_login):
    users = client.get('/admin/users', headers=admin_headers).json()
    target = next(u for u in users if u['username'] == 'operator')
    updated = client.patch(f"/admin/users/{target['id']}", headers=admin_headers, json={'role': 'administrator'})
    assert updated.status_code == 200
    assert updated.json()['role'] == 'administrator'

    operator_me = client.get('/auth/me', headers=module_login(client, 'operator'))
    assert operator_me.json()['role'] == 'administrator'

    # Put the role back so later tests see the seed state.
    restored = client.patch(f"/admin/users/{target['id']}", headers=admin_headers, json={'role': 'campus_operator'})
    assert restored.status_code == 200
    assert restored.json()['role'] == 'campus_operator'


def test_self_role_change_and_deactivation_refused(client, admin_headers):
    me = client.get('/auth/me', headers=admin_headers).json()
    demote = client.patch(f"/admin/users/{me['id']}", headers=admin_headers, json={'role': 'student'})
    assert demote.status_code == 400

    deactivate = client.patch(f"/admin/users/{me['id']}", headers=admin_headers, json={'is_active': False})
    assert deactivate.status_code == 400

    # The administrator is still usable after the refused mutations.
    assert client.get('/auth/me', headers=admin_headers).status_code == 200


def test_self_delete_refused(client, admin_headers):
    me = client.get('/auth/me', headers=admin_headers).json()
    deleted = client.delete(f"/admin/users/{me['id']}", headers=admin_headers)
    assert deleted.status_code == 400


def test_delete_user_204_and_login_stops_working(client, admin_headers):
    created = client.post(
        '/admin/users', headers=admin_headers,
        json={'username': 'tempuser', 'email': 'temp@northbridge.edu', 'password': 'demo-temp', 'role': 'student'},
    )
    assert created.status_code == 201
    user_id = created.json()['id']
    assert client.post('/auth/login', json={'username': 'tempuser', 'password': 'demo-temp'}).status_code == 200

    deleted = client.delete(f'/admin/users/{user_id}', headers=admin_headers)
    assert deleted.status_code == 204
    assert client.post('/auth/login', json={'username': 'tempuser', 'password': 'demo-temp'}).status_code == 401
