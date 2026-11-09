from __future__ import annotations

from ortools.sat.python import cp_model


class SolverOutcome:
    def __init__(self, raw_status: int, rows: list[dict]):
        self.raw_status = raw_status
        self.rows = rows


def generate_schedule_rows(institution_id: int, campus_id: int, sessions: list[dict], rooms: list[dict]) -> dict:
    model = cp_model.CpModel()
    assignments = {}

    for session in sessions:
        for room in rooms:
            var = model.NewBoolVar(f's_{session["id"]}_r_{room["id"]}')
            assignments[(session['id'], room['id'])] = var
        model.Add(sum(assignments[(session['id'], room['id'])] for room in rooms) == 1)

    for room in rooms:
        for idx_a, s1 in enumerate(sessions):
            for s2 in sessions[idx_a + 1:]:
                if s1['day'] != s2['day']:
                    continue
                start_a = s1['start_minute']
                end_a = s1['start_minute'] + s1['duration_minute']
                start_b = s2['start_minute']
                end_b = s2['start_minute'] + s2['duration_minute']
                if start_a < end_b and start_b < end_a:
                    model.Add(assignments[(s1['id'], room['id'])] + assignments[(s2['id'], room['id'])] <= 1)

    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    rows = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for session in sessions:
            chosen_room = next((room for room in rooms if solver.Value(assignments[(session['id'], room['id'])])), None)
            rows.append({
                'session_id': session['id'],
                'course': session.get('course_name', 'Course'),
                'room_id': chosen_room['id'] if chosen_room else None,
                'room': chosen_room['name'] if chosen_room else 'Unassigned',
                'day': session['day'],
                'start_minute': session['start_minute'],
                'duration_minute': session['duration_minute'],
            })
    return {'status': solver.StatusName(status), 'rows': rows}
