import { FormEvent, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { apiFetch } from '../api';
import LottieLoader from '../components/LottieLoader';
import type { Campus, MeResponse, OverviewResponse } from '../types';
import { STAFF_ROLES } from '../types';
import { useApi } from '../useApi';

interface GenerateResult {
  status: string;
  proposal_id: number;
  schedule: unknown[];
  metrics: Record<string, string | number>;
}

export default function DashboardPage() {
  const { me } = useOutletContext<{ me: MeResponse }>();
  const { data, error } = useApi<OverviewResponse>('/dashboard/overview');
  const isStaff = STAFF_ROLES.includes(me.role);

  const { data: campuses } = useApi<Campus[]>(isStaff ? `/institutions/${me.institution_id}/campuses` : null);
  const [generateNotice, setGenerateNotice] = useState('');
  const [generating, setGenerating] = useState(false);

  async function handleGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const campusId = Number(form.get('campus_id'));
    if (!campusId) {
      setGenerateNotice('Pick a campus first');
      return;
    }
    setGenerating(true);
    setGenerateNotice('');
    try {
      const result = await apiFetch<GenerateResult>('/schedules/generate', {
        method: 'POST',
        body: JSON.stringify({ institution_id: me.institution_id, campus_id: campusId }),
      });
      const violations = result.metrics.hard_constraint_violations;
      setGenerateNotice(
        `Solver ${result.status}: proposal #${result.proposal_id}, ${violations} hard-constraint violation(s).`,
      );
    } catch (generateError) {
      setGenerateNotice(generateError instanceof Error ? generateError.message : 'Generation failed');
    } finally {
      setGenerating(false);
    }
  }

  if (error) {
    return <p className="error-notice" role="alert">{error}</p>;
  }
  if (!data) {
    return <LottieLoader label="Loading overview…" />;
  }

  const stats: [string, number][] = [
    ['Campuses', data.campuses],
    ['Rooms', data.rooms],
    ['Courses', data.courses],
    ['Lecturers', data.lecturers],
    ['Student groups', data.student_groups],
    ['Sessions', data.sessions],
    ['Published', data.published_sessions],
    ['Pending proposals', data.pending_proposals],
  ];

  return (
    <>
      <header className="dashboard-header">
        <div>
          <h1>{data.institution_name}</h1>
          <p className="hint">
            Signed in as {me.full_name || me.username} — {me.role.replace('_', ' ')} view
          </p>
        </div>
        {isStaff && campuses && campuses.length > 0 && (
          <form className="generate-form" onSubmit={handleGenerate}>
            <label>
              Campus
              <select name="campus_id" defaultValue={String(campuses[0].id)} aria-label="Campus">
                {campuses.map((campus) => (
                  <option key={campus.id} value={campus.id}>
                    {campus.name}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit" disabled={generating}>
              {generating ? 'Solving…' : 'Generate schedule'}
            </button>
          </form>
        )}
      </header>

      {generateNotice && (
        <p className="notice" role="status">{generateNotice}</p>
      )}

      <div className="stats-grid">
        {stats.map(([label, value]) => (
          <div className="stat-card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>

      <div className="panel-grid">
        <section className="panel">
          <h3>What you can do here</h3>
          <p className="hint">
            {me.role === 'student' && 'Open “My schedule” for your cohort’s sessions and the 3D campus map.'}
            {me.role === 'faculty' && 'Review your teaching schedule, the shared timetable and your bookings.'}
            {me.role === 'campus_operator' && 'Manage rooms, approve proposals and publish the timetable.'}
            {me.role === 'administrator' && 'Full access: users, rooms, proposals and the audit trail.'}
          </p>
        </section>
        <section className="panel">
          <h3>Constraint engine</h3>
          <p className="hint">
            Generation runs Google OR-Tools CP-SAT against room overlap, lecturer, cohort, capacity and
            availability constraints. Nothing is published until an authorized approver accepts the proposal.
          </p>
        </section>
      </div>
    </>
  );
}
