import { fireEvent, screen, waitFor } from '@testing-library/react';
import { renderApp, signedInAs, stubFetch } from '../testUtils';

const USERS = [
  {
    id: 1,
    username: 'admin',
    email: 'admin@northbridge.edu',
    full_name: 'Alice Admin',
    role: 'administrator',
    institution_id: 1,
    is_active: true,
    student_group_id: null,
    lecturer_id: null,
    sso_linked: false,
  },
  {
    id: 4,
    username: 'student',
    email: 'student@northbridge.edu',
    full_name: 'Sara Student',
    role: 'student',
    institution_id: 1,
    is_active: true,
    student_group_id: 1,
    lecturer_id: null,
    sso_linked: false,
  },
];

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AdminUsersPage', () => {
  it('lists the tenant accounts with roles', async () => {
    stubFetch({ '/auth/me': signedInAs('administrator'), '/admin/users': USERS });
    renderApp('/admin/users');

    expect(await screen.findByRole('cell', { name: 'admin' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'Alice Admin' })).toBeInTheDocument();
    expect(screen.getAllByText('administrator').length).toBeGreaterThan(0);
    expect(screen.getByRole('cell', { name: 'student@northbridge.edu' })).toBeInTheDocument();
    expect(screen.getByText(/other tenants are never listed/)).toBeInTheDocument();
  });

  it('creates a user through POST /admin/users', async () => {
    const fetchMock = stubFetch({
      '/auth/me': signedInAs('administrator'),
      '/admin/users': (init?: RequestInit) =>
        init?.method === 'POST'
          ? {
              id: 9,
              username: 'newlect',
              email: 'newlect@northbridge.edu',
              full_name: 'New Lecturer',
              role: 'faculty',
              institution_id: 1,
              is_active: true,
              student_group_id: null,
              lecturer_id: null,
              sso_linked: false,
            }
          : USERS,
    });
    renderApp('/admin/users');

    fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'newlect' } });
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'newlect@northbridge.edu' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'demo-password' } });
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'faculty' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create user' }));

    await waitFor(() => {
      expect(screen.getByText(/Created newlect/)).toBeInTheDocument();
    });
    const createCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).includes('/admin/users') && String((init as RequestInit | undefined)?.method) === 'POST',
    );
    expect(createCall).toBeDefined();
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      username: 'newlect',
      email: 'newlect@northbridge.edu',
      password: 'demo-password',
      role: 'faculty',
    });
  });
});
