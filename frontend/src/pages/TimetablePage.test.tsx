import { fireEvent, screen } from '@testing-library/react';
import { makeSession, renderApp, signedInAs, stubFetch } from '../testUtils';

const VERSIONS = [
  {
    id: 18,
    version: 8,
    label: 'Fall week 1',
    published_by_email: 'operator@northbridge.edu',
    published_at: '2026-11-10T09:00:00',
    session_count: 2,
  },
];

const BASE_DIFF = {
  institution_id: 1,
  published_version: 8,
  published_label: 'Fall week 1',
  draft_session_count: 2,
  added: [],
  removed: [],
  moved: [],
};

const SNAPSHOT_ROW = {
  id: 12,
  campus_id: 1,
  course_id: 3,
  lecturer_id: 2,
  student_group_id: 1,
  room_id: 4,
  day: 1,
  start_minute: 540,
  duration_minute: 90,
  status: 'draft',
};

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
      // Registered before the plain timetable prefix so the substring
      // matcher cannot hand these requests the timetable payload.
      '/institutions/1/timetable/versions': [],
      '/institutions/1/timetable/diff': {
        institution_id: 1,
        published_version: null,
        published_label: null,
        draft_session_count: 2,
        added: [],
        removed: [],
        moved: [],
      },
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

  it('lists published versions and the draft diff without a publish button for faculty', async () => {
    // The more specific routes must be registered before the plain timetable
    // prefix, or stubFetch's substring matching would hand the timetable
    // payload to the versions/diff requests.
    stubFetch({
      '/auth/me': signedInAs('faculty'),
      '/institutions/1/timetable/versions': VERSIONS,
      '/institutions/1/timetable/diff': {
        ...BASE_DIFF,
        added: [SNAPSHOT_ROW],
        moved: [
          { id: 7, from: { ...SNAPSHOT_ROW, id: 7, day: 0 }, to: { ...SNAPSHOT_ROW, id: 7, day: 2 } },
        ],
      },
      '/institutions/1/timetable': { institution_id: 1, sessions: [makeSession()] },
    });
    renderApp('/timetable');

    await screen.findByTestId('version-8');
    expect(screen.getByText(/v8 · Fall week 1/)).toBeInTheDocument();
    expect(screen.getByText('Draft vs published version 8')).toBeInTheDocument();
    expect(screen.getByText('1 added · 0 removed · 1 moved (draft: 2 session(s))')).toBeInTheDocument();
    expect(screen.getByText('+ #12 · Tuesday 09:00–10:30 · room 4')).toBeInTheDocument();
    expect(screen.getByText(/#7 · Monday 09:00–10:30 · room 4/)).toBeInTheDocument();
    expect(screen.getByText(/#7 · Wednesday 09:00–10:30 · room 4/)).toBeInTheDocument();
    // Faculty may read versions and diffs but never publish.
    expect(screen.queryByRole('button', { name: 'Publish current timetable' })).not.toBeInTheDocument();
  });

  it('lets an administrator publish a new version and refresh the diff', async () => {
    let diffFetches = 0;
    stubFetch({
      '/auth/me': signedInAs('administrator'),
      '/institutions/1/timetable/publish': (init?: RequestInit) => {
        expect(init?.method).toBe('POST');
        expect(String(init?.body)).toContain('"label":"Mid-term cut"');
        return {
          id: 19,
          version: 9,
          label: 'Mid-term cut',
          published_by_email: 'administrator@northbridge.edu',
          published_at: '2026-11-11T17:00:00',
          session_count: 2,
        };
      },
      '/institutions/1/timetable/versions': VERSIONS,
      '/institutions/1/timetable/diff': () => {
        diffFetches += 1;
        return diffFetches === 1
          ? BASE_DIFF
          : {
              ...BASE_DIFF,
              published_version: 9,
              published_label: 'Mid-term cut',
              removed: [SNAPSHOT_ROW],
            };
      },
      '/institutions/1/timetable': { institution_id: 1, sessions: [makeSession()] },
    });
    renderApp('/timetable');

    await screen.findByTestId('version-8');
    fireEvent.change(screen.getByLabelText('Version label'), { target: { value: 'Mid-term cut' } });
    fireEvent.click(screen.getByRole('button', { name: 'Publish current timetable' }));

    // The new version is prepended and the diff is refetched against it.
    await screen.findByTestId('version-9');
    expect(screen.getByText(/v9 · Mid-term cut/)).toBeInTheDocument();
    expect(screen.getByText('Draft vs published version 9')).toBeInTheDocument();
    expect(screen.getByText('0 added · 1 removed · 0 moved (draft: 2 session(s))')).toBeInTheDocument();
    expect(screen.getByText('− #12 · Tuesday 09:00–10:30 · room 4')).toBeInTheDocument();
  });
});
