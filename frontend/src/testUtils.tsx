import { render } from '@testing-library/react';
import type { RenderResult } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from './App';
import { TOKEN_KEY } from './api';
import type { MeResponse, Role, ScheduleSession } from './types';

/** Pre-seed a signed-in session and return the matching /auth/me profile. */
export function signedInAs(role: Role, overrides: Partial<MeResponse> = {}): MeResponse {
  const me: MeResponse = {
    id: role === 'administrator' ? 1 : 4,
    username: role,
    email: `${role}@northbridge.edu`,
    full_name: 'Demo User',
    role,
    institution_id: 1,
    institution_name: 'Northbridge University',
    student_group_id: role === 'student' ? 1 : null,
    lecturer_id: role === 'faculty' ? 1 : null,
    ...overrides,
  };
  localStorage.setItem(TOKEN_KEY, 'test-session-token');
  return me;
}

/**
 * Install a fetch stub keyed by URL fragment. Matching requests resolve with
 * the mapped body (status 200); a mapped function receives the RequestInit and
 * returns the body (lets GET and POST share a path); unmatched requests
 * resolve with a 404 detail.
 */
export function stubFetch(routes: Record<string, unknown>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const key = Object.keys(routes).find((fragment) => url.includes(fragment));
    if (key === undefined) {
      return {
        ok: false,
        status: 404,
        json: async () => ({ detail: `no stub for ${url}` }),
      } as Response;
    }
    const mapped = routes[key];
    const body = typeof mapped === 'function' ? (mapped as (init?: RequestInit) => unknown)(init) : mapped;
    return {
      ok: true,
      status: 200,
      json: async () => body,
    } as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

/** Render the full app (auth provider + routes) at the given location. */
export function renderApp(initialPath: string): RenderResult {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <App />
    </MemoryRouter>,
  );
}

/** A well-formed schedule session row (matches booking_to_dict). */
export function makeSession(overrides: Partial<ScheduleSession> = {}): ScheduleSession {
  return {
    id: 1,
    campus_id: 1,
    course_id: 1,
    course_code: 'CS101',
    course_name: 'Intro to Computing',
    lecturer_id: 1,
    lecturer_name: 'Ada Reed',
    student_group_id: 1,
    student_group_name: 'CS Year 1',
    room_id: 1,
    room_name: 'A101',
    day: 0,
    day_name: 'Monday',
    start_minute: 540,
    start_time: '09:00',
    end_minute: 630,
    end_time: '10:30',
    duration_minute: 90,
    status: 'draft',
    ...overrides,
  };
}
