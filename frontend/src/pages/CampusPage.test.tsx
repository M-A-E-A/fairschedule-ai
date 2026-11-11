import { fireEvent, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { renderApp, signedInAs, stubFetch } from '../testUtils';
import { minuteToTime, occupiedRoomIds, timeToMinute } from './CampusPage';

// Canvas renders its scene children as DOM nodes, so tests can click a
// building (mesh) and read its material colour like a user interacting with
// the 3D view would.
vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children }: { children: ReactNode }) => (
    <div data-testid="campus-canvas">{children}</div>
  ),
}));

const CAMPUSES = [
  { id: 1, name: 'Main Campus', slug: 'main', width: 60, depth: 40, room_count: 3 },
  { id: 2, name: 'Tech Park', slug: 'tech-park', width: 40, depth: 30, room_count: 1 },
];

const ROOMS = [
  { id: 1, institution_id: 1, campus_id: 1, name: 'A101', capacity: 80, room_type: 'lecture', equipment: 'projector' },
  { id: 2, institution_id: 1, campus_id: 1, name: 'C315', capacity: 120, room_type: 'lecture', equipment: 'screen' },
  { id: 3, institution_id: 1, campus_id: 2, name: 'T12', capacity: 65, room_type: 'seminar', equipment: 'board' },
];

const COURSES = [
  { id: 10, code: 'CS101', name: 'Intro to Computing', required_room_type: 'lecture' },
  { id: 11, code: 'MA201', name: 'Linear Algebra', required_room_type: 'lecture' },
];
const LECTURERS = [{ id: 20, name: 'Ada Reed', email: 'ada@northbridge.edu' }];
const GROUPS = [{ id: 30, name: 'CS Year 1', size: 80 }];

// A101 runs 09:00–10:30 on Monday; C315 runs 14:00–15:30 on Tuesday.
const BOOKINGS = [
  { id: 100, institution_id: 1, campus_id: 1, course_id: 10, lecturer_id: 20, student_group_id: 30, room_id: 1, day: 0, start_minute: 540, duration_minute: 90, status: 'draft' },
  { id: 101, institution_id: 1, campus_id: 1, course_id: 11, lecturer_id: 20, student_group_id: 30, room_id: 2, day: 1, start_minute: 840, duration_minute: 90, status: 'draft' },
];

/**
 * The legend renders `<button><strong>Name</strong> — type, N seats · state</button>`,
 * so the full string lives in `textContent` but is split across child
 * elements — testing-library's default text matcher only reads direct text
 * nodes.
 */
function legendHas(text: string) {
  return (
    Array.from(document.querySelectorAll('.room-legend button')).some((item) =>
      (item.textContent ?? '').includes(text),
    )
  );
}

function legendButton(roomName: string) {
  return Array.from(document.querySelectorAll<HTMLButtonElement>('.room-legend button')).find(
    (item) => (item.textContent ?? '').includes(roomName),
  ) as HTMLButtonElement;
}

function sceneMesh(roomName: string) {
  return document.querySelector(`mesh[name="${roomName}"]`);
}

function stubCampusApi() {
  return stubFetch({
    '/auth/me': signedInAs('student'),
    '/institutions/1/campuses': CAMPUSES,
    '/institutions/1/rooms': ROOMS,
    '/institutions/1/bookings': BOOKINGS,
    '/institutions/1/courses': COURSES,
    '/institutions/1/lecturers': LECTURERS,
    '/institutions/1/student-groups': GROUPS,
  });
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('occupiedRoomIds (occupancy window semantics)', () => {
  it('counts a room occupied from the session start to just before its end', () => {
    const bookings = [
      { id: 1, institution_id: 1, campus_id: 1, course_id: 1, lecturer_id: 1, student_group_id: 1, room_id: 7, day: 2, start_minute: 540, duration_minute: 90, status: 'draft' },
    ];

    expect(occupiedRoomIds(bookings, 2, 540)).toContain(7); // start is inclusive
    expect(occupiedRoomIds(bookings, 2, 629)).toContain(7); // one minute before the end
    expect(occupiedRoomIds(bookings, 2, 630)).toEqual(new Set()); // end is exclusive
    expect(occupiedRoomIds(bookings, 2, 539)).toEqual(new Set()); // one minute before the start
    expect(occupiedRoomIds(bookings, 3, 540)).toEqual(new Set()); // different day
    expect(occupiedRoomIds([], 2, 540)).toEqual(new Set()); // nothing booked anywhere
  });

  it('parses and formats clock times', () => {
    expect(timeToMinute('09:00')).toBe(540);
    expect(timeToMinute('14:30')).toBe(870);
    expect(timeToMinute(' 8:05 ')).toBe(485);
    expect(timeToMinute('not-a-time')).toBe(0);
    expect(minuteToTime(540)).toBe('09:00');
    expect(minuteToTime(870)).toBe('14:30');
  });
});

describe('CampusPage (3D campus view)', () => {
  it('renders the canvas and the occupancy legend for the selected campus', async () => {
    stubCampusApi();
    renderApp('/campus');

    expect(await screen.findByRole('heading', { name: '3D campus' })).toBeInTheDocument();
    expect(await screen.findByTestId('campus-canvas')).toBeInTheDocument();
    expect(screen.getByText('Main Campus · 2 building(s) · occupancy on Monday at 09:00')).toBeInTheDocument();
    // A101 has a Monday 09:00–10:30 session, so it is occupied at 09:00;
    // C315's only session is on Tuesday, so it is free now.
    expect(legendHas('A101 — lecture, 80 seats · occupied')).toBe(true);
    expect(legendHas('C315 — lecture, 120 seats · free')).toBe(true);
    expect(legendHas('T12 — seminar')).toBe(false);
  });

  it('switches to another campus on selection', async () => {
    stubCampusApi();
    renderApp('/campus');

    await screen.findByTestId('campus-canvas');
    fireEvent.change(screen.getByLabelText('Select campus'), { target: { value: '2' } });

    await screen.findByText('Tech Park · 1 building(s) · occupancy on Monday at 09:00');
    expect(legendHas('T12 — seminar, 65 seats · free')).toBe(true);
    expect(legendHas('A101 — lecture')).toBe(false);
  });

  it('recolors occupancy when the day and time window change', async () => {
    stubCampusApi();
    renderApp('/campus');

    await screen.findByTestId('campus-canvas');
    const a101 = legendButton('A101');
    const c315 = legendButton('C315');
    const a101Mesh = sceneMesh('A101');
    const c315Mesh = sceneMesh('C315');
    expect(a101Mesh?.querySelector('meshstandardmaterial')).toHaveAttribute('color', '#f87171');
    expect(c315Mesh?.querySelector('meshstandardmaterial')).toHaveAttribute('color', '#34d399');

    // Monday 11:00 — A101's morning session has ended.
    fireEvent.change(screen.getByLabelText('Select time'), { target: { value: '11:00' } });
    expect(a101.className).toContain('room-free');
    expect(c315.className).toContain('room-free');
    expect(sceneMesh('A101')?.querySelector('meshstandardmaterial')).toHaveAttribute('color', '#34d399');

    // Tuesday 14:00 — C315's afternoon session is running.
    fireEvent.change(screen.getByLabelText('Select day'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Select time'), { target: { value: '14:00' } });
    expect(a101.className).toContain('room-free');
    expect(c315.className).toContain('room-occupied');
    expect(sceneMesh('C315')?.querySelector('meshstandardmaterial')).toHaveAttribute('color', '#f87171');
    expect(screen.getByText('Main Campus · 2 building(s) · occupancy on Tuesday at 14:00')).toBeInTheDocument();
  });

  it('shows the selected room’s schedule from a legend click', async () => {
    stubCampusApi();
    renderApp('/campus');

    await screen.findByTestId('campus-canvas');
    fireEvent.click(legendButton('A101'));

    const panel = await screen.findByRole('region', { name: 'A101 schedule' });
    expect(panel).toHaveTextContent('A101 · Monday');
    expect(panel).toHaveTextContent('09:00–10:30');
    expect(panel).toHaveTextContent('CS101 · Intro to Computing');
    expect(panel).toHaveTextContent('Ada Reed');
    expect(panel).toHaveTextContent('CS Year 1');
    expect(legendButton('A101')).toHaveAttribute('aria-pressed', 'true');

    // Switching the day re-scopes the same room's panel.
    fireEvent.change(screen.getByLabelText('Select day'), { target: { value: '1' } });
    expect(screen.getByRole('region', { name: 'A101 schedule' })).toHaveTextContent(
      'No sessions in A101 on Tuesday.',
    );
  });

  it('selects a room by clicking its building in the 3D scene', async () => {
    stubCampusApi();
    renderApp('/campus');

    await screen.findByTestId('campus-canvas');
    fireEvent.click(sceneMesh('C315') as Element);

    const panel = await screen.findByRole('region', { name: 'C315 schedule' });
    expect(panel).toHaveTextContent('C315 · Monday');
    expect(panel).toHaveTextContent('No sessions in C315 on Monday.');
  });
});
