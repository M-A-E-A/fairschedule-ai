"""OR-Tools CP-SAT timetabling engine.

Hard constraints (all enforced, see docs/PROJECT.md):

* room overlap        — two sessions cannot occupy the same room at the same time
* lecturer conflict   — a lecturer cannot teach two sessions at the same time
* student-group clash — a cohort cannot be in two sessions at the same time
* capacity            — a room must seat the whole student group
* room type           — a course that requires e.g. a lab only gets lab rooms
* availability window — sessions fit inside the configured day window
* duration            — every session keeps its full duration

Soft objectives (minimised, in priority order by weight):

* preserve the original time and room where practical
* prefer earlier sessions
* avoid undesirable (late) slots
* reduce large gaps inside a student group's day
* fairness: penalise the *squared* count of undesirable slots per group and
  per lecturer so bad slots do not cluster on the same cohort/teacher

The solver only proposes. An authorised user must approve the proposal
through the API before any booking is mutated.

Strategy: a deterministic greedy pass computes a conflict-free assignment in
milliseconds. It seeds CP-SAT as a solution hint and acts as the fallback when
the solver cannot prove optimality inside its time budget, so generation
always returns a usable schedule whenever one exists.
"""

from __future__ import annotations

import time
from collections import defaultdict

from ortools.sat.python import cp_model

# Weights (objective units ~ minutes).
W_PRESERVE_TIME = 20000
W_PRESERVE_ROOM = 2000
W_UNDESIRABLE = 800
W_FAIRNESS = 100
W_GAP = 30  # per hour of gap over the threshold
W_EARLIER = 1

GAP_THRESHOLD_MINUTES = 120
UNDESIRABLE_AFTER_MINUTE = 960  # 16:00 and later
DAY_MINUTES = 1440
# Larger than any absolute start (5 days * 1440); used for empty min/max.
BIG_TIME = 100000
# CP-SAT's generic probing pass alone can consume the whole time budget on
# larger instances; capping it keeps generation responsive.
PROBING_DETERMINISTIC_TIME_LIMIT = 0.05


def count_hard_violations(sessions: list[dict], rooms: list[dict], rows: list[dict]) -> int:
    """Independently verify a set of assigned rows against the hard constraints."""
    rooms_by_id = {room['id']: room for room in rooms}
    sessions_by_id = {session['id']: session for session in sessions}
    violations = 0
    seen: list[tuple] = []
    for row in rows:
        session = sessions_by_id.get(row['session_id'])
        room = rooms_by_id.get(row['room_id'])
        if session is None or room is None:
            violations += 1
            continue
        if room['capacity'] < session.get('headcount', 0):
            violations += 1
        required = session.get('required_room_type', 'any')
        if required not in ('any', '', None) and room['room_type'] != required:
            violations += 1
        if row['start_minute'] < session.get('day_start', 0):
            violations += 1
        end = row['start_minute'] + row['duration_minute']
        if end > session.get('day_end', DAY_MINUTES):
            violations += 1
        for key, value in (
            ('room', row['room_id']),
            ('lecturer', session.get('lecturer_id')),
            ('group', session.get('student_group_id')),
        ):
            if value is None:
                continue
            for other_key, other_value, other_day, other_start, other_end in seen:
                if other_key != key or other_value != value or other_day != row['day']:
                    continue
                if row['start_minute'] < other_end and other_start < end:
                    violations += 1
            seen.append((key, value, row['day'], row['start_minute'], end))
    return violations


def _slot_options(
    session: dict,
    days: list[int],
    day_start: int,
    day_end: int,
    slot_minutes: int,
    allow_time_change: bool,
) -> list[tuple[int, int]]:
    """(day, start_minute) choices for a session, honouring its availability."""
    duration = session['duration_minute']
    if not allow_time_change:
        original_day = session.get('original_day')
        original_start = session.get('original_start_minute')
        if (
            original_day in days
            and original_start is not None
            and day_start <= original_start
            and original_start + duration <= day_end
        ):
            return [(original_day, original_start)]
        return []
    slots: list[tuple[int, int]] = []
    for day in days:
        start = day_start
        while start + duration <= day_end:
            slots.append((day, start))
            start += slot_minutes
    return slots


def _overlaps(busy: list | None, day: int, start: int, end: int) -> bool:
    if not busy:
        return False
    return any(
        other_day == day and start < other_end and other_start < end
        for other_day, other_start, other_end in busy
    )


def _greedy_assignment(
    sessions: list[dict], options_by_session: dict[int, list[tuple[tuple[int, int], dict]]]
) -> dict[int, tuple[tuple[int, int], dict]] | None:
    """Deterministic first-fit assignment honouring every hard constraint.

    Longest sessions first (hardest to place), earliest slot, first eligible
    room. Returns None as soon as one session cannot be placed.
    """
    busy_rooms: dict[int, list] = defaultdict(list)
    busy_lecturers: dict[int, list] = defaultdict(list)
    busy_groups: dict[int, list] = defaultdict(list)
    chosen: dict[int, tuple[tuple[int, int], dict]] = {}
    for session in sorted(sessions, key=lambda item: (-item['duration_minute'], item['id'])):
        placed = False
        for (day, start), room in options_by_session[session['id']]:
            end = start + session['duration_minute']
            if _overlaps(busy_rooms[room['id']], day, start, end):
                continue
            lecturer_id = session.get('lecturer_id')
            group_id = session.get('student_group_id')
            if lecturer_id is not None and _overlaps(busy_lecturers[lecturer_id], day, start, end):
                continue
            if group_id is not None and _overlaps(busy_groups[group_id], day, start, end):
                continue
            chosen[session['id']] = ((day, start), room)
            busy_rooms[room['id']].append((day, start, end))
            if lecturer_id is not None:
                busy_lecturers[lecturer_id].append((day, start, end))
            if group_id is not None:
                busy_groups[group_id].append((day, start, end))
            placed = True
            break
        if not placed:
            return None
    return chosen


def _build_result(
    sessions: list[dict],
    rooms: list[dict],
    chosen: dict[int, tuple[tuple[int, int], dict]],
    solver_status: str,
    solution_source: str,
    elapsed_ms: int,
) -> dict:
    """Turn a chosen (day, start, room) map into rows plus solver metrics."""
    rows = []
    soft_matches = 0
    undesirable = 0
    changes = 0
    for session in sessions:
        pick = chosen.get(session['id'])
        if pick is None:
            continue
        (day, start), room = pick
        if (
            session.get('original_day') == day
            and session.get('original_start_minute') == start
            and session.get('original_room_id') == room['id']
        ):
            soft_matches += 1
        if start >= UNDESIRABLE_AFTER_MINUTE:
            undesirable += 1
        if session.get('original_day') is not None and (
            session.get('original_day') != day or session.get('original_start_minute') != start
        ):
            changes += 1
        rows.append({
            'session_id': session['id'],
            'course': session.get('course', 'Course'),
            'room_id': room['id'],
            'room': room['name'],
            'day': day,
            'start_minute': start,
            'duration_minute': session['duration_minute'],
            'lecturer_id': session.get('lecturer_id'),
            'student_group_id': session.get('student_group_id'),
        })
    rows.sort(key=lambda row: (row['day'], row['start_minute'], row['room']))
    return {
        'status': solver_status,
        'rows': rows,
        'metrics': {
            'solver_status': solver_status,
            'solution_source': solution_source,
            'hard_constraint_violations': count_hard_violations(sessions, rooms, rows),
            'soft_preference_matches': soft_matches,
            'undesirable_slots': undesirable,
            'changes_during_repair': changes,
            'time_to_generate_ms': elapsed_ms,
        },
    }


def _failed_result(solver_status: str, elapsed_ms: int) -> dict:
    return {
        'status': solver_status,
        'rows': [],
        'metrics': {
            'solver_status': solver_status,
            'solution_source': 'none',
            'hard_constraint_violations': None,
            'soft_preference_matches': 0,
            'undesirable_slots': 0,
            'changes_during_repair': 0,
            'time_to_generate_ms': elapsed_ms,
        },
    }


def generate_schedule_rows(
    sessions: list[dict],
    rooms: list[dict],
    *,
    institution_id: int,
    campus_id: int,
    days: list[int] | None = None,
    day_start: int = 480,
    day_end: int = 1080,
    slot_minutes: int = 30,
    allow_time_change: bool = True,
    time_limit_seconds: float = 10.0,
) -> dict:
    """Assign a time and a room to every session under all hard constraints."""
    started = time.perf_counter()
    days = days if days is not None else [0, 1, 2, 3, 4]
    model = cp_model.CpModel()

    options_by_session: dict[int, list[tuple[tuple[int, int], dict]]] = {}
    structurally_infeasible = False
    for session in sessions:
        slots = _slot_options(session, days, day_start, day_end, slot_minutes, allow_time_change)
        headcount = session.get('headcount', 0)
        required = session.get('required_room_type', 'any')
        required_ok = required in ('any', '', None)
        feasible_rooms = [
            room for room in rooms if room['capacity'] >= headcount and (required_ok or room['room_type'] == required)
        ]
        # A session with no feasible (slot, room) combination cannot be placed.
        options = [((day, start), room) for (day, start) in slots for room in feasible_rooms]
        if not options:
            structurally_infeasible = True
            continue
        options_by_session[session['id']] = options

    if structurally_infeasible or len(options_by_session) != len({s['id'] for s in sessions}):
        # Capacity, room type or availability cannot be satisfied: CP-SAT would
        # report INFEASIBLE anyway, so short-circuit with the same status.
        return _failed_result('INFEASIBLE', int((time.perf_counter() - started) * 1000))

    # Deterministic greedy warm start (also the fallback solution).
    greedy_choice = _greedy_assignment(sessions, options_by_session)

    assign: dict[tuple[int, int, int, int], cp_model.IntVar] = {}
    time_indicators: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
    intervals_by_room: dict[int, list] = defaultdict(list)
    intervals_by_lecturer: dict[int, list] = defaultdict(list)
    intervals_by_group: dict[int, list] = defaultdict(list)

    for session in sessions:
        session_vars = []
        for (day, start), room in options_by_session[session['id']]:
            var = model.new_bool_var(f's{session["id"]}_d{day}_t{start}_r{room["id"]}')
            assign[(session['id'], day, start, room['id'])] = var
            session_vars.append(var)
            absolute_start = day * DAY_MINUTES + start
            interval = model.new_optional_interval_var(
                start=absolute_start,
                size=session['duration_minute'],
                end=absolute_start + session['duration_minute'],
                is_present=var,
                name=f'iv_s{session["id"]}_d{day}_t{start}_r{room["id"]}',
            )
            intervals_by_room[room['id']].append(interval)
            if session.get('lecturer_id') is not None:
                intervals_by_lecturer[session['lecturer_id']].append(interval)
            if session.get('student_group_id') is not None:
                intervals_by_group[session['student_group_id']].append(interval)
            time_indicators[(session['id'], day, start)].append(var)
        # Exactly one (time, room) choice per session.
        model.add(sum(session_vars) == 1)

    # Hard: no two sessions share a room, lecturer or cohort at the same time.
    for room_intervals in intervals_by_room.values():
        model.add_no_overlap(room_intervals)
    for lecturer_intervals in intervals_by_lecturer.values():
        model.add_no_overlap(lecturer_intervals)
    for group_intervals in intervals_by_group.values():
        model.add_no_overlap(group_intervals)

    # y[s][day][start]: this session occupies that time slot (any room).
    y: dict[tuple[int, int, int], cp_model.IntVar] = {}
    for (session_id, day, start), vars_at_slot in time_indicators.items():
        var = model.new_bool_var(f'y_s{session_id}_d{day}_t{start}')
        model.add(var == sum(vars_at_slot))
        y[(session_id, day, start)] = var

    objective_terms: list = []

    # Soft: preserve original time/room, prefer earlier, avoid late slots.
    undesirable_by_group: dict[int, list] = defaultdict(list)
    undesirable_by_lecturer: dict[int, list] = defaultdict(list)
    for session in sessions:
        original_day = session.get('original_day')
        original_start = session.get('original_start_minute')
        original_room_id = session.get('original_room_id')
        for (day, start), room in options_by_session[session['id']]:
            var = assign[(session['id'], day, start, room['id'])]
            absolute = day * DAY_MINUTES + start
            objective_terms.append(W_EARLIER * absolute * var)
            if start >= UNDESIRABLE_AFTER_MINUTE:
                objective_terms.append(W_UNDESIRABLE * var)
                if session.get('student_group_id') is not None:
                    undesirable_by_group[session['student_group_id']].append(var)
                if session.get('lecturer_id') is not None:
                    undesirable_by_lecturer[session['lecturer_id']].append(var)
            if original_day is not None and original_start is not None:
                if (day, start) != (original_day, original_start):
                    objective_terms.append(W_PRESERVE_TIME * var)
            if original_room_id is not None and room['id'] != original_room_id:
                objective_terms.append(W_PRESERVE_ROOM * var)

    # Soft: anti-clustering fairness — penalise (count of undesirable slots)^2
    # per student group and per lecturer so bad slots do not pile onto one cohort.
    for owners, by_owner in (('g', undesirable_by_group), ('l', undesirable_by_lecturer)):
        for owner_id, owner_vars in by_owner.items():
            if len(owner_vars) < 2:
                continue
            count_var = model.new_int_var(0, len(owner_vars), f'bad_{owners}{owner_id}')
            model.add(count_var == sum(owner_vars))
            square_var = model.new_int_var(0, len(owner_vars) ** 2, f'bad2_{owners}{owner_id}')
            model.add_multiplication_equality(square_var, [count_var, count_var])
            objective_terms.append(W_FAIRNESS * square_var)

    # Soft: reduce large gaps inside each group's day.
    y_by_session_day: dict[tuple[int, int], list[tuple[int, cp_model.IntVar]]] = defaultdict(list)
    for (session_id, day, start), var in y.items():
        y_by_session_day[(session_id, day)].append((start, var))
    grouped_sessions: dict[int, list[dict]] = defaultdict(list)
    for session in sessions:
        if session.get('student_group_id') is not None:
            grouped_sessions[session['student_group_id']].append(session)
    for group_id, group_sessions in grouped_sessions.items():
        for day in days:
            starts_expr: list = []
            ends_expr: list = []
            duration_terms: list = []
            for session in group_sessions:
                duration = session['duration_minute']
                day_choices = y_by_session_day.get((session['id'], day), [])
                start_var = model.new_int_var(0, BIG_TIME, f'gmin_s{session["id"]}_d{day}')
                end_var = model.new_int_var(0, BIG_TIME, f'gmax_s{session["id"]}_d{day}')
                if day_choices:
                    start_expr = sum(start * var for start, var in day_choices)
                    end_expr = sum((start + duration) * var for start, var in day_choices)
                    presence = sum(var for _, var in day_choices)
                    model.add(start_var == start_expr + BIG_TIME * (1 - presence))
                    model.add(end_var == end_expr)
                    duration_terms.append(duration * presence)
                else:
                    model.add(start_var == BIG_TIME)
                    model.add(end_var == 0)
                starts_expr.append(start_var)
                ends_expr.append(end_var)
            if not starts_expr:
                continue
            min_start = model.new_int_var(0, BIG_TIME, f'first_g{group_id}_d{day}')
            max_end = model.new_int_var(0, BIG_TIME, f'last_g{group_id}_d{day}')
            model.add_min_equality(min_start, starts_expr)
            model.add_max_equality(max_end, ends_expr)
            total_duration = sum(duration_terms) if duration_terms else 0
            gap_var = model.new_int_var(0, BIG_TIME, f'gap_g{group_id}_d{day}')
            model.add(gap_var >= max_end - min_start - total_duration - GAP_THRESHOLD_MINUTES)
            model.add(gap_var >= 0)
            objective_terms.append(W_GAP * gap_var)

    # Solution hint from the greedy pass: gives CP-SAT a feasible incumbent.
    if greedy_choice is not None:
        for (session_id, day, start, room_id), var in assign.items():
            pick = greedy_choice.get(session_id)
            picked = pick is not None and pick[0] == (day, start) and pick[1]['id'] == room_id
            model.add_hint(var, int(picked))

    model.minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.log_search_progress = False
    solver.parameters.probing_deterministic_time_limit = PROBING_DETERMINISTIC_TIME_LIMIT
    solver.parameters.presolve_probing_deterministic_time_limit = PROBING_DETERMINISTIC_TIME_LIMIT
    status = solver.Solve(model)
    status_name = solver.StatusName(status)
    elapsed = int((time.perf_counter() - started) * 1000)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        chosen: dict[int, tuple[tuple[int, int], dict]] = {}
        for session in sessions:
            for (day, start), room in options_by_session[session['id']]:
                if solver.value(assign[(session['id'], day, start, room['id'])]):
                    chosen[session['id']] = ((day, start), room)
                    break
        return _build_result(sessions, rooms, chosen, status_name, 'ortools_cp_sat', elapsed)
    if greedy_choice is not None:
        # The solver did not prove optimality in time, but the warm start is a
        # verified feasible schedule; return it with the honest solver status.
        return _build_result(sessions, rooms, greedy_choice, status_name, 'greedy_fallback', elapsed)
    return _failed_result(status_name, elapsed)


def find_booking_conflicts(candidate: dict, existing: list[dict]) -> list[str]:
    """Return the kinds of hard conflict ``candidate`` would create.

    Used to reject overlapping room/lecturer/group bookings at write time,
    so violations never reach the database. Kinds are ``room_conflict``,
    ``lecturer_conflict`` and ``group_conflict``.
    """
    start = candidate['start_minute']
    end = start + candidate['duration_minute']
    conflicts: set[str] = set()
    for other in existing:
        if other['id'] == candidate.get('id'):
            continue
        if other['day'] != candidate['day']:
            continue
        other_start = other['start_minute']
        other_end = other_start + other['duration_minute']
        if not (start < other_end and other_start < end):
            continue
        if other['room_id'] == candidate['room_id']:
            conflicts.add('room_conflict')
        if other['lecturer_id'] == candidate['lecturer_id']:
            conflicts.add('lecturer_conflict')
        if other['student_group_id'] == candidate['student_group_id']:
            conflicts.add('group_conflict')
    return sorted(conflicts)
