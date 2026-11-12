import { fireEvent, screen, within } from '@testing-library/react';
import { renderApp, signedInAs, stubFetch } from '../testUtils';
import type { AuditEvent } from '../types';

/** 25 events, deliberately sent oldest-first so the page's own ordering is
 * what the test observes. Every third id is a proposal approval. */
const EVENTS: AuditEvent[] = Array.from({ length: 25 }, (_, index) => {
  const id = index + 1;
  return {
    id,
    user_email: `user${id}@northbridge.edu`,
    event_type: id % 3 === 0 ? 'proposal_approved' : id % 2 === 0 ? 'schedule_generated' : 'csv_import',
    message: `Event #${id} recorded`,
  };
});

function auditRoutes(role: 'administrator' | 'campus_operator' | 'student') {
  return {
    '/auth/me': signedInAs(role),
    '/audit-events': EVENTS,
    '/dashboard/overview': {
      institution_id: 1,
      institution_name: 'Northbridge University',
      campuses: 2,
      rooms: 4,
      courses: 3,
      lecturers: 3,
      student_groups: 3,
      sessions: 3,
      published_sessions: 0,
      pending_proposals: 0,
      role,
    },
    '/me/schedule': { role, scope: role === 'student' ? 'student' : 'institution', sessions: [] },
  };
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AuditPage', () => {
  it('renders the timeline newest first with pagination', async () => {
    stubFetch(auditRoutes('administrator'));
    renderApp('/admin/audit');

    expect(await screen.findByRole('heading', { name: 'Audit timeline' })).toBeInTheDocument();
    expect(screen.getByText('25 of 25 event(s) — newest first')).toBeInTheDocument();
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();

    // Oldest-first payload, but the first data row is the newest event.
    const rows = screen.getAllByRole('row');
    expect(within(rows[1]).getByText('25')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Event #25 recorded')).toBeInTheDocument();
    expect(within(rows[10]).getByText('16')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument();
    const page2 = screen.getAllByRole('row');
    expect(within(page2[1]).getByText('15')).toBeInTheDocument();
    expect(within(page2[1]).getByText('user15@northbridge.edu')).toBeInTheDocument();

    // Last page holds the remaining 5 events and disables Next.
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('Page 3 of 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    expect(screen.getAllByRole('row')).toHaveLength(6); // header + 5 events

    fireEvent.click(screen.getByRole('button', { name: 'Previous' }));
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous' })).toBeEnabled();
  });

  it('filters by event type and recomputes pagination', async () => {
    stubFetch(auditRoutes('administrator'));
    renderApp('/admin/audit');

    fireEvent.change(await screen.findByLabelText('Filter by event type'), {
      target: { value: 'proposal_approved' },
    });

    expect(screen.getByText('8 of 25 event(s) — newest first')).toBeInTheDocument();
    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument();
    const rows = screen.getAllByRole('row');
    expect(rows).toHaveLength(9); // header + 8 approvals
    // Only approvals in the visible rows, newest (id 24) first.
    expect(within(rows[1]).getByText('24')).toBeInTheDocument();
    expect(screen.queryByText('Event #25 recorded')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();

    // Filtering from page 3 must not leave the user stranded on a page that
    // no longer exists (page state resets to 0).
    fireEvent.change(screen.getByLabelText('Filter by event type'), { target: { value: 'all' } });
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('Page 3 of 3')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Filter by event type'), {
      target: { value: 'schedule_generated' },
    });
    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument();
  });

  async function expectBouncedOffAuditPage(
    role: 'campus_operator' | 'student',
    landing: { name: RegExp; level?: 1 | 2 | 3 },
  ) {
    const fetchMock = stubFetch(auditRoutes(role));
    renderApp('/admin/audit');

    // The route guard redirects before AuditPage mounts, so the admin-only
    // endpoint is never fetched for these roles.
    expect(await screen.findByRole('heading', landing)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Audit timeline' })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/audit-events'))).toBe(false);
  }

  it('bounces campus operators off the audit page without fetching its data', async () => {
    await expectBouncedOffAuditPage('campus_operator', { name: /^Northbridge University$/ });
  });

  it('bounces students off the audit page without fetching its data', async () => {
    await expectBouncedOffAuditPage('student', { name: /^My schedule$/ });
  });

  it('shows an error notice when the endpoint refuses the request', async () => {
    // No '/audit-events' stub: the request resolves as a 404 detail and the
    // page surfaces the failure instead of rendering an empty timeline.
    stubFetch({ '/auth/me': signedInAs('administrator') });
    renderApp('/admin/audit');

    expect(await screen.findByRole('alert')).toHaveTextContent(/no stub for/);
    expect(screen.queryByRole('heading', { name: 'Audit timeline' })).not.toBeInTheDocument();
  });
});
