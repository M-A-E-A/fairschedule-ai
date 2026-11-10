import { screen } from '@testing-library/react';
import { makeSession, renderApp, signedInAs, stubFetch } from '../testUtils';

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('TimetablePage', () => {
  it('renders the institution timetable for staff', async () => {
    stubFetch({
      '/auth/me': signedInAs('campus_operator'),
      '/institutions/1/timetable': {
        institution_id: 1,
        sessions: [
          makeSession(),
          makeSession({
            id: 2,
            day: 1,
            day_name: 'Tuesday',
            course_code: 'DBS201',
            start_time: '10:00',
            end_time: '11:30',
            room_name: 'B204',
            status: 'published',
          }),
        ],
      },
    });
    renderApp('/timetable');

    expect(await screen.findByRole('heading', { name: 'Institution timetable' })).toBeInTheDocument();
    expect(screen.getByText('2 scheduled session(s) across all campuses')).toBeInTheDocument();
    expect(screen.getByText('Monday')).toBeInTheDocument();
    expect(screen.getByText('B204')).toBeInTheDocument();
    expect(screen.getByText('published')).toBeInTheDocument();
  });

  it('redirects students to their own schedule', async () => {
    stubFetch({
      '/auth/me': signedInAs('student'),
      '/me/schedule': { role: 'student', scope: 'student', sessions: [] },
    });
    renderApp('/timetable');

    expect(await screen.findByRole('heading', { name: 'My schedule' })).toBeInTheDocument();
  });
});
