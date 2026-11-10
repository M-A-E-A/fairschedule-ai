import { screen } from '@testing-library/react';
import { renderApp, signedInAs, stubFetch } from '../testUtils';

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RequireRole route guards', () => {
  it('sends anonymous visitors to the login screen', async () => {
    stubFetch({});
    renderApp('/dashboard');

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('blocks students from the administrator user list', async () => {
    const me = signedInAs('student');
    stubFetch({
      '/auth/me': me,
      '/me/schedule': { role: 'student', scope: 'student', sessions: [] },
    });
    renderApp('/admin/users');

    expect(await screen.findByRole('heading', { name: 'My schedule' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Users' })).not.toBeInTheDocument();
  });

  it('blocks students from the staff timetable', async () => {
    const me = signedInAs('student');
    stubFetch({
      '/auth/me': me,
      '/me/schedule': { role: 'student', scope: 'student', sessions: [] },
    });
    renderApp('/timetable');

    expect(await screen.findByRole('heading', { name: 'My schedule' })).toBeInTheDocument();
  });

  it('keeps a signed-in administrator on the user list', async () => {
    const me = signedInAs('administrator');
    stubFetch({ '/auth/me': me, '/admin/users': [] });
    renderApp('/admin/users');

    expect(await screen.findByRole('heading', { name: 'Users' })).toBeInTheDocument();
  });
});
