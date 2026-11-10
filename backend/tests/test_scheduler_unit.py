"""Unit tests for the OR-Tools engine: hard constraints, metrics, repair."""

from __future__ import annotations

from app.services.scheduler import count_hard_violations, find_booking_conflicts, generate_schedule_rows


def _room(room_id: int = 1, capacity: int = 60, room_type: str = 'lecture', name: str | None = None) -> dict:
    return {'id': room_id, 'name': name or f'Room {room_id}', 'capacity': capacity, 'room_type': room_type}


def _session(
    session_id: int,
    *,
    day: int | None = 0,
    start: int | None = 540,
    room_id: int | None = 1,
    lecturer_id: int | None = 1,
    group_id: int | None = 1,
    headcount: int = 30,
    duration: int = 90,
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
        'headcount': headcount,
        'duration_minute': duration,
        'original_day': day,
        'original_start_minute': start,
        'original_room_id': room_id,
        'day_start': day_start,
        'day_end': day_end,
    }


def _generate(sessions, rooms, **kwargs):
    kwargs.setdefault('institution_id', 1)
    kwargs.setdefault('campus_id', 1)
    return generate_schedule_rows(sessions, rooms, **kwargs)


def test_capacity_too_small_is_infeasible():
    sessions = [_session(1, headcount=60)]
    rooms = [_room(capacity=40)]
    result = _generate(sessions, rooms, allow_time_change=False)
    assert result['status'] == 'INFEASIBLE'
    assert result['rows'] == []
    assert result['metrics']['solution_source'] == 'none'


def test_required_room_type_is_enforced():
    sessions = [_session(1, required_room_type='lab')]
    rooms = [_room(room_type='lecture')]
    result = _generate(sessions, rooms, allow_time_change=False)
    assert result['status'] == 'INFEASIBLE'

    # The same session fits once a lab room is available.
    result = _generate(sessions, rooms + [_room(2, room_type='lab')], allow_time_change=False)
    assert result['status'] != 'INFEASIBLE'
    assert result['rows'][0]['room_id'] == 2


def test_lecturer_conflict_fixed_slot_is_infeasible_but_movable_solves():
    # Two sessions, same lecturer, same original slot: with the original times
    # pinned the instance is genuinely infeasible.
    sessions = [
        _session(1, lecturer_id=7, group_id=1),
        _session(2, lecturer_id=7, group_id=2, start=630, room_id=2),
    ]
    rooms = [_room(1), _room(2)]
    fixed = _generate(sessions, rooms, allow_time_change=False)
    assert fixed['status'] == 'INFEASIBLE'

    # Movable: the solver finds a conflict-free placement with zero violations.
    movable = _generate(sessions, rooms)
    assert movable['status'] != 'INFEASIBLE'
    assert movable['metrics']['hard_constraint_violations'] == 0
    assert count_hard_violations(sessions, rooms, movable['rows']) == 0


def test_student_group_conflict_is_detected():
    sessions = [
        _session(1, group_id=3, lecturer_id=1),
        _session(2, group_id=3, lecturer_id=2, start=630, room_id=2),
    ]
    rooms = [_room(1), _room(2)]
    fixed = _generate(sessions, rooms, allow_time_change=False)
    assert fixed['status'] == 'INFEASIBLE'

    movable = _generate(sessions, rooms)
    assert movable['status'] != 'INFEASIBLE'
    assert movable['metrics']['hard_constraint_violations'] == 0


def test_room_overlap_fixed_slot_is_infeasible_but_movable_solves():
    sessions = [
        _session(1, lecturer_id=1, group_id=1),
        _session(2, lecturer_id=2, group_id=2, start=630, room_id=1),
    ]
    rooms = [_room(1)]
    fixed = _generate(sessions, rooms, allow_time_change=False)
    assert fixed['status'] == 'INFEASIBLE'

    movable = _generate(sessions, rooms)
    assert movable['status'] != 'INFEASIBLE'
    assert movable['metrics']['hard_constraint_violations'] == 0


def test_feasible_instance_reports_all_metrics():
    sessions = [_session(1), _session(2, lecturer_id=2, group_id=2, start=630, room_id=2)]
    rooms = [_room(1), _room(2)]
    result = _generate(sessions, rooms)
    metrics = result['metrics']
    assert set(metrics) >= {
        'solver_status',
        'solution_source',
        'hard_constraint_violations',
        'soft_preference_matches',
        'undesirable_slots',
        'changes_during_repair',
        'time_to_generate_ms',
    }
    assert metrics['hard_constraint_violations'] == 0
    assert metrics['solution_source'] in ('ortools_cp_sat', 'greedy_fallback')
    assert metrics['time_to_generate_ms'] >= 0
    assert len(result['rows']) == 2


def test_repair_does_not_modify_input_sessions():
    sessions = [_session(1), _session(2, lecturer_id=2, group_id=2, start=630, room_id=2)]
    before = [dict(s) for s in sessions]
    _generate(sessions, [_room(1), _room(2)])
    assert sessions == before


def test_find_booking_conflicts_kinds():
    existing = [
        {'id': 1, 'day': 0, 'start_minute': 540, 'duration_minute': 90, 'room_id': 1,
         'lecturer_id': 5, 'student_group_id': 9},
    ]
    # Same room and time: room conflict.
    candidate = {'day': 0, 'start_minute': 540, 'duration_minute': 60, 'room_id': 1, 'lecturer_id': 6,
                 'student_group_id': 10}
    kinds = find_booking_conflicts(candidate, existing)
    assert 'room_conflict' in kinds
    assert 'lecturer_conflict' not in kinds

    # Same lecturer, different room.
    candidate = {'day': 0, 'start_minute': 600, 'duration_minute': 60, 'room_id': 2, 'lecturer_id': 5,
                 'student_group_id': 10}
    assert 'lecturer_conflict' in find_booking_conflicts(candidate, existing)

    # Same group, overlapping window.
    candidate = {'day': 0, 'start_minute': 600, 'duration_minute': 60, 'room_id': 3, 'lecturer_id': 6,
                 'student_group_id': 9}
    assert 'group_conflict' in find_booking_conflicts(candidate, existing)

    # A free slot reports no conflicts at all.
    candidate = {'day': 1, 'start_minute': 540, 'duration_minute': 60, 'room_id': 1, 'lecturer_id': 5,
                 'student_group_id': 9}
    assert find_booking_conflicts(candidate, existing) == []
