"""S-01: solver wall-clock limit, honest UNKNOWN status, env-var configuration.

Three properties are pinned down, mirroring the scope item's acceptance
criteria:

* a solvable instance inside the budget returns a complete schedule;
* an artificially tiny budget makes CP-SAT report ``UNKNOWN`` — the response
  never presents a partial result as a full schedule (the deterministic
  greedy fallback still places *every* session under all hard constraints)
  and never crashes;
* the default budget is configured through ``SOLVER_TIME_LIMIT_SECONDS`` and
  a request without an explicit ``time_limit_seconds`` inherits it.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings, get_settings
from app.services.scheduler import count_hard_violations, generate_schedule_rows
from fastapi.testclient import TestClient


def _room(room_id: int, capacity: int = 120, room_type: str = 'lecture') -> dict:
    return {'id': room_id, 'name': f'Room {room_id}', 'capacity': capacity, 'room_type': room_type}


def _session(
    session_id: int,
    *,
    day: int = 0,
    start: int = 540,
    room_id: int = 1,
    lecturer_id: int = 1,
    group_id: int = 1,
    required_room_type: str = 'any',
    day_start: int = 480,
    day_end: int = 1080,
) -> dict:
    return {
        'id': session_id,
        'course': f'Course {session_id}',
        'course_code': f'C{session_id}',
        'required_room_type': required_room_type,
        'lecturer_id': lecturer_id,
        'student_group_id': group_id,
        'headcount': 30,
        'duration_minute': 90,
        'original_day': day,
        'original_start_minute': start,
        'original_room_id': room_id,
        'day_start': day_start,
        'day_end': day_end,
    }


def _seeded_campus_sessions() -> list[dict]:
    """The seeded Northbridge main-campus instance (CS101/DBS201/MTH120)."""
    return [
        _session(1, lecturer_id=1, group_id=1, room_id=1),
        _session(2, day=0, start=600, room_id=2, lecturer_id=2, group_id=2, required_room_type='lab'),
        _session(3, day=1, start=540, room_id=1, lecturer_id=3, group_id=1),
    ]


def _seeded_campus_rooms() -> list[dict]:
    return [_room(1, capacity=80), _room(2, capacity=40, room_type='lab'), _room(3, capacity=120)]


def test_solvable_instance_within_default_limit(client: TestClient, faculty_headers: dict):
    """(a) The seeded instance solves inside the configured budget."""
    response = client.post(
        '/schedules/generate',
        headers=faculty_headers,
        json={'institution_id': 1, 'campus_id': 1},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] in ('OPTIMAL', 'FEASIBLE')
    # Every seeded session is placed; nothing is dropped or partial.
    assert len(body['schedule']) == 3
    assert body['metrics']['hard_constraint_violations'] == 0
    assert body['metrics']['solver_status'] == body['status']
    # docs/PROJECT.md evaluation metrics: solve time and status are exposed.
    assert body['metrics']['time_to_generate_ms'] >= 0


def test_tiny_limit_reports_unknown_and_still_returns_full_schedule():
    """(b) An artificially tiny budget reports UNKNOWN honestly.

    CP-SAT cannot prove anything inside 1e-7 s. The response must say
    ``UNKNOWN`` (never claim OPTIMAL), and the fallback it serves is a
    *complete* conflict-free schedule — a partial result must never be
    presented as a full one. The call must not crash.
    """
    sessions = _seeded_campus_sessions()
    rooms = _seeded_campus_rooms()
    result = generate_schedule_rows(
        sessions, rooms, institution_id=1, campus_id=1, time_limit_seconds=1e-7
    )
    assert result['status'] == 'UNKNOWN'
    assert result['metrics']['solver_status'] == 'UNKNOWN'
    assert result['metrics']['solution_source'] == 'greedy_fallback'
    # All three sessions placed, zero hard-constraint violations.
    assert len(result['rows']) == 3
    assert count_hard_violations(sessions, rooms, result['rows']) == 0
    assert result['metrics']['hard_constraint_violations'] == 0
    assert result['metrics']['time_to_generate_ms'] >= 0


@pytest.fixture
def tiny_solver_limit(monkeypatch: pytest.MonkeyPatch):
    """Make the configured default budget one no solver can finish in.

    The cached Settings instance is patched in place (the same pattern
    ``tests/test_sso.py`` uses) rather than rebuilt through
    ``get_settings.cache_clear()``: several modules hold their own reference
    to the cached instance, and replacing the cache would silently fork the
    configuration objects mid-session.
    """
    monkeypatch.setattr(get_settings(), 'solver_time_limit_seconds', 1e-7)


def test_env_var_maps_into_settings(monkeypatch: pytest.MonkeyPatch):
    """(c) SOLVER_TIME_LIMIT_SECONDS configures the Settings default."""
    monkeypatch.setenv('SOLVER_TIME_LIMIT_SECONDS', '2.5')
    assert Settings(_env_file=None).solver_time_limit_seconds == 2.5


def test_env_configured_default_budget_reaches_the_solver(
    client: TestClient, faculty_headers: dict, tiny_solver_limit: None
):
    """(c) A request without an explicit limit inherits the configured one."""
    assert get_settings().solver_time_limit_seconds == 1e-7
    response = client.post(
        '/schedules/generate',
        headers=faculty_headers,
        json={'institution_id': 1, 'campus_id': 1},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # The tiny default budget reached the solver: honest UNKNOWN with the
    # complete fallback schedule, exactly like the direct engine call.
    assert body['status'] == 'UNKNOWN'
    assert body['metrics']['solver_status'] == 'UNKNOWN'
    assert body['metrics']['solution_source'] == 'greedy_fallback'
    assert len(body['schedule']) == 3


def test_explicit_request_limit_still_overrides_the_default(
    client: TestClient, faculty_headers: dict, tiny_solver_limit: None
):
    """The request field remains a per-call override of the configured default."""
    assert get_settings().solver_time_limit_seconds == 1e-7
    response = client.post(
        '/schedules/generate',
        headers=faculty_headers,
        json={'institution_id': 1, 'campus_id': 1, 'time_limit_seconds': 5.0},
    )
    assert response.status_code == 200, response.text
    assert response.json()['status'] in ('OPTIMAL', 'FEASIBLE')


def test_default_settings_ship_a_ten_second_budget():
    """The documented default is 10 seconds."""
    assert Settings(_env_file=None).solver_time_limit_seconds == 10.0
    assert get_settings().solver_time_limit_seconds > 0
