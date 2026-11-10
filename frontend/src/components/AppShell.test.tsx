import { fireEvent, screen, waitFor } from '@testing-library/react';
import { makeSession, renderApp, signedInAs, stubFetch } from '../testUtils';

function routes(role: 'administrator' | 'student') {
  return {
    '/auth/me': signedInAs(role),
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
    '/me/schedule': { role, scope: role === 'student' ? 'student' : 'institution', sessions: [makeSession()] },
  };
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AppShell navigation is role-aware', () => {
  it('shows administrators the staff and admin entries', async () => {
    stubFetch(routes('administrator'));
    renderApp('/dashboard');

    const nav = await screen.findByRole('navigation', { name: 'Main navigation' });
    const labels = [...nav.querySelectorAll('a')].map((link) => link.textContent);
    expect(labels).toContain('Overview');
    expect(labels).toContain('My schedule');
    expect(labels).toContain('Timetable');
    expect(labels).toContain('Rooms');
    expect(labels).toContain('Users');
    expect(labels).toContain('3D campus');
    expect(screen.getByTestId('role-badge')).toHaveTextContent('administrator');
  });

  it('hides timetable, rooms and users from students', async () => {
    stubFetch(routes('student'));
    renderApp('/schedule');

    const nav = await screen.findByRole('navigation', { name: 'Main navigation' });
    const labels = [...nav.querySelectorAll('a')].map((link) => link.textContent);
    expect(labels).toContain('My schedule');
    expect(labels).toContain('3D campus');
    expect(labels).not.toContain('Timetable');
    expect(labels).not.toContain('Rooms');
    expect(labels).not.toContain('Users');
    expect(screen.getByTestId('role-badge')).toHaveTextContent('student');
  });

  it('signs out and returns to the login screen', async () => {
    stubFetch(routes('administrator'));
    renderApp('/dashboard');

    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    });
    expect(localStorage.getItem('fairschedule_token')).toBeNull();
  });
});
