import { FormEvent, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { apiFetch } from '../api';
import LottieLoader from '../components/LottieLoader';
import type {
  BookingSnapshotRow,
  MeResponse,
  ScheduleSession,
  TimetableDiffResponse,
  TimetableResponse,
  TimetableVersionEntry,
} from '../types';
import { PROPOSAL_APPROVER_ROLES } from '../types';
import { useApi } from '../useApi';

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

function formatMinute(minute: number): string {
  const hours = Math.floor(minute / 60);
  const minutes = minute % 60;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
}

/** Human label for a frozen booking row (diff entries carry ids only). */
function formatChange(row: BookingSnapshotRow): string {
  const day = DAY_NAMES[row.day] ?? String(row.day);
  const time = `${formatMinute(row.start_minute)}–${formatMinute(row.start_minute + row.duration_minute)}`;
  return `#${row.id} · ${day} ${time} · room ${row.room_id}`;
}

export default function TimetablePage() {
  const { me } = useOutletContext<{ me: MeResponse }>();
  const { data, error } = useApi<TimetableResponse>(`/institutions/${me.institution_id}/timetable`);
  // Publishing (S-06): versions and the draft-vs-published diff ride the
  // same staff-gated page; both fetches are tolerated to fail silently.
  const { data: fetchedVersions } = useApi<TimetableVersionEntry[]>(
    `/institutions/${me.institution_id}/timetable/versions`,
  );
  const { data: fetchedDiff } = useApi<TimetableDiffResponse>(
    `/institutions/${me.institution_id}/timetable/diff`,
  );
  const [versions, setVersions] = useState<TimetableVersionEntry[] | null>(null);
  const [diff, setDiff] = useState<TimetableDiffResponse | null>(null);
  const [notice, setNotice] = useState('');
  const [publishing, setPublishing] = useState(false);

  const canPublish = PROPOSAL_APPROVER_ROLES.includes(me.role);
  const versionList = versions ?? fetchedVersions;
  const diffData = diff ?? fetchedDiff;

  async function handlePublish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const label = String(new FormData(form).get('label') ?? '').trim();
    setPublishing(true);
    setNotice('');
    try {
      const published = await apiFetch<TimetableVersionEntry>(
        `/institutions/${me.institution_id}/timetable/publish`,
        { method: 'POST', body: JSON.stringify({ label }) },
      );
      setVersions([published, ...(versionList ?? [])]);
      setDiff(await apiFetch<TimetableDiffResponse>(`/institutions/${me.institution_id}/timetable/diff`));
      form.reset();
    } catch (publishError) {
      setNotice(publishError instanceof Error ? publishError.message : 'Could not publish the timetable');
    } finally {
      setPublishing(false);
    }
  }

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

      <section className="panel publish-panel" aria-label="Timetable publishing">
        <h3>Published versions</h3>
        {canPublish && (
          <form className="publish-form" onSubmit={handlePublish}>
            <label>
              Label
              <input name="label" aria-label="Version label" placeholder="optional" maxLength={120} />
            </label>
            <button type="submit" disabled={publishing}>
              {publishing ? 'Publishing…' : 'Publish current timetable'}
            </button>
          </form>
        )}
        {notice && <p className="error-notice" role="alert">{notice}</p>}
        {versionList !== null && versionList.length === 0 && (
          <p className="empty-state">Nothing published yet.</p>
        )}
        <ul className="version-list">
          {(versionList ?? []).map((version) => (
            <li key={version.id} data-testid={`version-${version.version}`}>
              <strong>
                v{version.version} · {version.label}
              </strong>{' '}
              — {version.session_count} session(s), by {version.published_by_email}
            </li>
          ))}
        </ul>

        {diffData && (
          <div className="diff-summary" data-testid="timetable-diff">
            <h4>
              {diffData.published_version === null
                ? 'Draft vs published (nothing published yet)'
                : `Draft vs published version ${diffData.published_version}`}
            </h4>
            <p className="hint">
              {diffData.added.length} added · {diffData.removed.length} removed · {diffData.moved.length}{' '}
              moved (draft: {diffData.draft_session_count} session(s))
            </p>
            <ul className="diff-list">
              {diffData.added.map((row) => (
                <li key={`added-${row.id}`} className="diff-added">
                  + {formatChange(row)}
                </li>
              ))}
              {diffData.removed.map((row) => (
                <li key={`removed-${row.id}`} className="diff-removed">
                  − {formatChange(row)}
                </li>
              ))}
              {diffData.moved.map((change) => (
                <li key={`moved-${change.id}`} className="diff-moved">
                  ↦ {formatChange(change.from)} → {formatChange(change.to)}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </>
  );
}
