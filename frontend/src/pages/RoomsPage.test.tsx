import { fireEvent, screen, waitFor } from '@testing-library/react';
import { renderApp, signedInAs, stubFetch } from '../testUtils';

const ROOMS = [
  { id: 1, institution_id: 1, campus_id: 1, name: 'A101', capacity: 80, room_type: 'lecture', equipment: 'projector' },
  { id: 2, institution_id: 1, campus_id: 2, name: 'T12', capacity: 65, room_type: 'seminar', equipment: 'whiteboard' },
];

const CAMPUSES = [
  { id: 1, name: 'Main Campus', slug: 'main', width: 60, depth: 40, room_count: 1 },
  { id: 2, name: 'Tech Park', slug: 'tech-park', width: 40, depth: 30, room_count: 1 },
];

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RoomsPage', () => {
  it('lists the tenant rooms with their campuses', async () => {
    stubFetch({
      '/auth/me': signedInAs('faculty'),
      '/institutions/1/rooms': ROOMS,
      '/institutions/1/campuses': CAMPUSES,
    });
    renderApp('/rooms');

    expect(await screen.findByRole('cell', { name: 'A101' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'Tech Park' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '80' })).toBeInTheDocument();
    // Faculty may manage bookings but not room allocation: no create form.
    expect(screen.queryByRole('button', { name: 'Add room' })).not.toBeInTheDocument();
  });

  it('lets a campus operator create a room', async () => {
    const fetchMock = stubFetch({
      '/auth/me': signedInAs('campus_operator'),
      '/institutions/1/rooms': (init?: RequestInit) =>
        init?.method === 'POST'
          ? {
              id: 3,
              institution_id: 1,
              campus_id: 1,
              name: 'NEW-101',
              capacity: 42,
              room_type: 'lecture',
              equipment: '',
            }
          : ROOMS,
      '/institutions/1/campuses': CAMPUSES,
    });
    renderApp('/rooms');

    fireEvent.change(await screen.findByLabelText('Room name'), { target: { value: 'NEW-101' } });
    fireEvent.change(screen.getByLabelText('Capacity'), { target: { value: '42' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add room' }));

    await waitFor(() => {
      expect(screen.getByRole('cell', { name: 'NEW-101' })).toBeInTheDocument();
    });
    const createCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).includes('/institutions/1/rooms') &&
        String((init as RequestInit | undefined)?.method) === 'POST',
    );
    expect(createCall).toBeDefined();
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      name: 'NEW-101',
      capacity: 42,
      campus_id: 1,
      room_type: 'lecture',
    });
  });
});
