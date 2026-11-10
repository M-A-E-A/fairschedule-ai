import { useOutletContext } from 'react-router-dom';
import LottieLoader from '../components/LottieLoader';
import type { MeResponse, ScheduleResponse, ScheduleSession } from '../types';
import { useApi } from '../useApi';

const DAY_ORDER = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

function SessionList({ sessions }: { sessions: ScheduleSession[] }) {
  const grouped = [...sessions].sort((a, b) => a.day - b.day || a.start_minute - b.start_minute);
  const days = [...new Set(grouped.map((session) => session.day_name))];

  if (grouped.length === 0) {
    return <p className="empty-state">No sessions are scheduled for you yet.</p>;
  }

  return (
    <div className="schedule-days">
      {days.sort((a, b) => DAY_ORDER.indexOf(a) - DAY_ORDER.indexOf(b)).map((day) => (
        <section className="panel schedule-day" key={day}>
          <h3>{day}</h3>
          <ul className="session-list">
            {grouped
              .filter((session) => session.day_name === day)
              .map((session) => (
                <li className="session-card" key={session.id} data-testid={`session-${session.id}`}>
                  <div className="session-time">
                    <strong>{session.start_time}</strong>
                    <span>–{session.end_time}</span>
                  </div>
                  <div className="session-body">
                    <span className="session-course">
                      {session.course_code} · {session.course_name}
                    </span>
                    <span className="session-meta">
                      {session.room_name} · {session.lecturer_name} · {session.student_group_name}
                    </span>
                  </div>
                  <span className={`status-badge status-${session.status}`}>{session.status}</span>
                </li>
              ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export default function MySchedulePage() {
  const { me } = useOutletContext<{ me: MeResponse }>();
  const { data, error } = useApi<ScheduleResponse>('/me/schedule');

  if (error) {
    return <p className="error-notice" role="alert">{error}</p>;
  }
  if (!data) {
    return <LottieLoader label="Loading your schedule…" />;
  }

  const scopeLabel: Record<ScheduleResponse['scope'], string> = {
    student: `${me.full_name || me.username}'s cohort schedule`,
    lecturer: 'Your teaching schedule',
    institution: 'Full institutional schedule',
  };

  return (
    <>
      <header className="dashboard-header">
        <div>
          <h1>My schedule</h1>
          <p className="hint">{scopeLabel[data.scope]}</p>
        </div>
        <span className="role-badge">{data.sessions.length} sessions</span>
      </header>
      <SessionList sessions={data.sessions} />
    </>
  );
}
