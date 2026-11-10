import { screen } from '@testing-library/react';
import { makeSession, renderApp, signedInAs, stubFetch } from '../testUtils';

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('MySchedulePage (GET /me/schedule)', () => {
  it('renders the student cohort schedule returned by the backend', async () => {
    const sessions = [
      makeSession({ id: 1, day: 0, day_name: 'Monday', start_time: '09:00', end_time: '10:30' }),
      makeSession({
        id: 2,
        day: 1,
        day_name: 'Tuesday',
        start_minute: 600,
        start_time: '10:00',
        end_minute: 690,
        end_time: '11:30',
        course_code: 'MTH120',
        course_name: 'Discrete Mathematics',
        room_name: 'C315',
      }),
    ];
    stubFetch({
      '/auth/me': signedInAs('student'),
      '/me/schedule': { role: 'student', scope: 'student', sessions },
    });
    renderApp('/schedule');

    expect(await screen.findByRole('heading', { name: 'My schedule' })).toBeInTheDocument();
    expect(screen.getByText('2 sessions')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Monday' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Tuesday' })).toBeInTheDocument();
    expect(screen.getByTestId('session-1')).toHaveTextContent('CS101');
    expect(screen.getByTestId('session-2')).toHaveTextContent('MTH120');
    expect(screen.getByTestId('session-2')).toHaveTextContent('10:00');
    expect(screen.getByText(/cohort schedule/)).toBeInTheDocument();
  });

  it('shows an explicit empty state when the cohort has no sessions', async () => {
    stubFetch({
      '/auth/me': signedInAs('student'),
      '/me/schedule': { role: 'student', scope: 'student', sessions: [] },
    });
    renderApp('/schedule');

    expect(await screen.findByText(/No sessions are scheduled for you yet/)).toBeInTheDocument();
  });
});
