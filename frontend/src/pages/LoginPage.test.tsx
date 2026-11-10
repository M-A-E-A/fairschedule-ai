import { fireEvent, screen, waitFor } from '@testing-library/react';
import { makeSession, renderApp, signedInAs, stubFetch } from '../testUtils';

const SSO_OFF = { enabled: false, provider: 'none', login_url: '', client_id: '', redirect_uri: '' };

function baseRoutes() {
  return {
    '/auth/sso/config': SSO_OFF,
    '/auth/me': signedInAs('administrator'),
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
      pending_proposals: 1,
      role: 'administrator',
    },
    '/me/schedule': { role: 'student', scope: 'student', sessions: [makeSession()] },
  };
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('LoginPage sign-in methods', () => {
  it('signs in with a username and password', async () => {
    const fetchMock = stubFetch(baseRoutes());
    renderApp('/login');

    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'demo-admin' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    await screen.findByRole('heading', { name: 'Northbridge University' });

    const loginCall = fetchMock.mock.calls.find(([, init]) =>
      String((init as RequestInit | undefined)?.body).includes('"username"'),
    );
    expect(loginCall).toBeDefined();
    const body = JSON.parse(String(loginCall?.[1]?.body));
    expect(body).toEqual({ username: 'admin', password: 'demo-admin' });
    expect(String(loginCall?.[0])).toContain('/auth/login');
  });

  it('signs in with an email and password', async () => {
    const fetchMock = stubFetch(baseRoutes());
    renderApp('/login');

    fireEvent.click(screen.getByRole('tab', { name: 'Email' }));
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'admin@northbridge.edu' },
    });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'demo-admin' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    await screen.findByRole('heading', { name: 'Northbridge University' });

    const loginCall = fetchMock.mock.calls.find(([, init]) =>
      String((init as RequestInit | undefined)?.body).includes('"email"'),
    );
    expect(loginCall).toBeDefined();
    expect(JSON.parse(String(loginCall?.[1]?.body))).toEqual({
      email: 'admin@northbridge.edu',
      password: 'demo-admin',
    });
  });

  it('shows the server error for rejected credentials', async () => {
    stubFetch({ '/auth/sso/config': SSO_OFF });
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes('/auth/login')) {
          return { ok: false, status: 401, json: async () => ({ detail: 'invalid credentials' }) } as Response;
        }
        return { ok: true, status: 200, json: async () => ({}) } as Response;
      }),
    );
    renderApp('/login');

    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong-password' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    await screen.findByRole('alert');
    expect(screen.getByRole('alert')).toHaveTextContent('invalid credentials');
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('sends students to their own schedule after sign-in', async () => {
    stubFetch({
      '/auth/sso/config': SSO_OFF,
      '/auth/me': signedInAs('student'),
      '/me/schedule': { role: 'student', scope: 'student', sessions: [makeSession()] },
    });
    renderApp('/login');

    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'student' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'demo-student' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    await screen.findByRole('heading', { name: 'My schedule' });
    expect(await screen.findByTestId('session-1')).toBeInTheDocument();
  });

  it('offers single sign-on when the backend reports it enabled', async () => {
    stubFetch({
      '/auth/sso/config': {
        enabled: true,
        provider: 'google',
        login_url: '/auth/sso/login',
        client_id: 'client-123',
        redirect_uri: 'http://localhost:8000/auth/sso/callback',
      },
    });
    renderApp('/login');

    const ssoLink = await screen.findByRole('link', { name: /Continue with google sign-on/i });
    expect(ssoLink).toHaveAttribute('href', 'http://localhost:8000/auth/sso/login');
  });

  it('restores a session from the SSO callback fragment', async () => {
    window.location.hash = '#access_token=sso-token';
    stubFetch({
      '/auth/sso/config': SSO_OFF,
      '/auth/me': signedInAs('administrator'),
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
        role: 'administrator',
      },
    });

    renderApp('/login');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Northbridge University' })).toBeInTheDocument();
    });
    expect(localStorage.getItem('fairschedule_token')).toBe('sso-token');
    window.location.hash = '';
  });
});
