import { useOutletContext } from 'react-router-dom';
import LottieLoader from '../components/LottieLoader';
import type { MeResponse, ScheduleSession, TimetableResponse } from '../types';
import { useApi } from '../useApi';

export default function TimetablePage() {
  const { me } = useOutletContext<{ me: MeResponse }>();
  const { data, error } = useApi<TimetableResponse>(`/institutions/${me.institution_id}/timetable`);

  if (error) {
    return <p className="error-notice" role="alert">{error}</p>;
  }
  if (!data) {
    return <LottieLoader label="Loading timetable…" />;
  }

  const rows = [...data.sessions].sort((a, b) => a.day - b.day || a.start_minute - b.start_minute);

  return (
    <>
      <header className="dashboard-header">
        <div>
          <h1>Institution timetable</h1>
          <p className="hint">{rows.length} scheduled session(s) across all campuses</p>
        </div>
      </header>
      <section className="panel">
        <table>
          <thead>
            <tr>
              <th>Day</th>
              <th>Time</th>
              <th>Course</th>
              <th>Lecturer</th>
              <th>Cohort</th>
              <th>Room</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row: ScheduleSession) => (
              <tr key={row.id}>
                <td>{row.day_name}</td>
                <td>
                  {row.start_time}–{row.end_time}
                </td>
                <td>
                  {row.course_code} <span className="hint">{row.course_name}</span>
                </td>
                <td>{row.lecturer_name}</td>
                <td>{row.student_group_name}</td>
                <td>{row.room_name}</td>
                <td>
                  <span className={`status-badge status-${row.status}`}>{row.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="empty-state">No sessions scheduled yet.</p>}
      </section>
    </>
  );
}
