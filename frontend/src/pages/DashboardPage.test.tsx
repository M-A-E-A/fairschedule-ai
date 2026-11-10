import { screen } from '@testing-library/react';
import { renderApp, signedInAs, stubFetch } from '../testUtils';

const OVERVIEW = {
  institution_id: 1,
  institution_name: 'Northbridge University',
  campuses: 2,
  rooms: 4,
  courses: 3,
  lecturers: 3,
  student_groups: 3,
  sessions: 3,
  published_sessions: 1,
  pending_proposals: 5,
  role: 'administrator',
};

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('DashboardPage', () => {
  it('renders live overview statistics for the institution', async () => {
    stubFetch({ '/auth/me': signedInAs('administrator'), '/dashboard/overview': OVERVIEW });
    renderApp('/dashboard');

    expect(await screen.findByRole('heading', { name: 'Northbridge University' })).toBeInTheDocument();
    expect(screen.getByText('Campuses')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('Pending proposals')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText(/administrator view/)).toBeInTheDocument();
  });

  it('offers schedule generation to staff roles only', async () => {
    stubFetch({
      '/auth/me': signedInAs('administrator'),
      '/dashboard/overview': OVERVIEW,
      '/institutions/1/campuses': [
        { id: 1, name: 'Main Campus', slug: 'main', width: 60, depth: 40, room_count: 3 },
      ],
    });
    renderApp('/dashboard');

    expect(await screen.findByRole('button', { name: 'Generate schedule' })).toBeInTheDocument();
  });

  it('hides schedule generation from students', async () => {
    stubFetch({
      '/auth/me': signedInAs('student'),
      '/dashboard/overview': { ...OVERVIEW, role: 'student' },
      '/me/schedule': { role: 'student', scope: 'student', sessions: [] },
    });
    renderApp('/dashboard');

    expect(await screen.findByRole('heading', { name: 'Northbridge University' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Generate schedule' })).not.toBeInTheDocument();
  });
});
