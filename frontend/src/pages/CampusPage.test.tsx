import { fireEvent, screen, waitFor } from '@testing-library/react';
import { renderApp, signedInAs, stubFetch } from '../testUtils';

vi.mock('@react-three/fiber', () => ({
  Canvas: () => <div data-testid="campus-canvas" />,
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

/**
 * The legend renders `<li><strong>Name</strong> — type, N seats</li>`, so the
 * full string lives in `textContent` but is split across a child element —
 * testing-library's default text matcher only reads direct text nodes.
 */
function legendHas(text: string) {
  return (
    Array.from(document.querySelectorAll('li')).some((item) =>
      (item.textContent ?? '').includes(text),
    )
  );
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('CampusPage (3D campus view)', () => {
  it('renders the canvas and the plain list view of the selected campus', async () => {
    stubFetch({
      '/auth/me': signedInAs('student'),
      '/institutions/1/campuses': CAMPUSES,
      '/institutions/1/rooms': ROOMS,
    });
    renderApp('/campus');

    expect(await screen.findByRole('heading', { name: '3D campus' })).toBeInTheDocument();
    expect(await screen.findByTestId('campus-canvas')).toBeInTheDocument();
    expect(screen.getByText('Main Campus · 2 building(s) shown, sized by capacity')).toBeInTheDocument();
    expect(legendHas('A101 — lecture, 80 seats')).toBe(true);
    expect(legendHas('T12 — seminar')).toBe(false);
  });

  it('switches to another campus on selection', async () => {
    stubFetch({
      '/auth/me': signedInAs('student'),
      '/institutions/1/campuses': CAMPUSES,
      '/institutions/1/rooms': ROOMS,
    });
    renderApp('/campus');

    await screen.findByTestId('campus-canvas');
    fireEvent.change(screen.getByLabelText('Select campus'), { target: { value: '2' } });

    await waitFor(() => {
      expect(legendHas('T12 — seminar, 65 seats')).toBe(true);
    });
    expect(legendHas('A101 — lecture')).toBe(false);
  });
});
