import { useMemo, useState } from 'react';
import LottieLoader from '../components/LottieLoader';
import type { AuditEvent } from '../types';
import { useApi } from '../useApi';

/** Rows per page of the timeline. */
const PAGE_SIZE = 10;

/**
 * Administrator-only audit timeline (S-09): renders the existing
 * `GET /audit-events` endpoint, newest event first, with pagination and an
 * event-type filter. The route guard in App.tsx already keeps other roles
 * off this page, and the backend refuses to serve them the data anyway.
 */
export default function AuditPage() {
  const { data: events, error } = useApi<AuditEvent[]>('/audit-events');
  const [eventType, setEventType] = useState('all');
  const [page, setPage] = useState(0);

  // Newest first by id, whatever order the server sends.
  const newestFirst = useMemo(() => [...(events ?? [])].sort((a, b) => b.id - a.id), [events]);
  const eventTypes = useMemo(
    () => [...new Set(newestFirst.map((event) => event.event_type))].sort(),
    [newestFirst],
  );
  const filtered = useMemo(
    () => (eventType === 'all' ? newestFirst : newestFirst.filter((event) => event.event_type === eventType)),
    [newestFirst, eventType],
  );

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const visible = filtered.slice(currentPage * PAGE_SIZE, currentPage * PAGE_SIZE + PAGE_SIZE);

  if (error) {
    return <p className="error-notice" role="alert">{error}</p>;
  }
  if (!events) {
    return <LottieLoader label="Loading audit timeline…" />;
  }

  function handleFilterChange(value: string) {
    setEventType(value);
    setPage(0);
  }

  return (
    <>
      <header className="dashboard-header">
        <div>
          <h1>Audit timeline</h1>
          <p className="hint">
            {filtered.length} of {newestFirst.length} event(s) — newest first
          </p>
        </div>
        <label>
          Filter by event type
          <select
            aria-label="Filter by event type"
            value={eventType}
            onChange={(event) => handleFilterChange(event.target.value)}
          >
            <option value="all">All event types</option>
            {eventTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
      </header>

      <section className="panel" aria-label="Audit events">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Event</th>
              <th>Detail</th>
              <th>User</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((event) => (
              <tr key={event.id}>
                <td>{event.id}</td>
                <td>
                  <span className="status-badge">{event.event_type}</span>
                </td>
                <td>{event.message}</td>
                <td>{event.user_email}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {visible.length === 0 && <p className="empty-state">No audit events match this filter.</p>}
      </section>

      <nav className="panel" aria-label="Audit timeline pagination">
        <button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>
          Previous
        </button>
        <span aria-live="polite">
          Page {currentPage + 1} of {pageCount}
        </span>
        <button
          type="button"
          disabled={currentPage >= pageCount - 1}
          onClick={() => setPage(currentPage + 1)}
        >
          Next
        </button>
      </nav>
    </>
  );
}
