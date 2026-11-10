/**
 * Thin API client shared by every page.
 *
 * All configuration comes from the environment (VITE_API_BASE_URL, see
 * docker-compose.yml and .env.example) with a development default that
 * matches the backend's default port.
 */
import type { AuthToken, MeResponse } from './types';

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000';

export const TOKEN_KEY = 'fairschedule_token';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

interface ApiFetchInit extends RequestInit {
  /** Override the stored session token (used during sign-in). */
  token?: string | null;
}

/** Fetch JSON from the API with bearer auth, JSON headers and error mapping. */
export async function apiFetch<T>(path: string, init: ApiFetchInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && init.body !== null) {
    headers.set('Content-Type', 'application/json');
  }
  const token = init.token !== undefined ? init.token : localStorage.getItem(TOKEN_KEY);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') {
        detail = body.detail;
      } else if (body.detail !== undefined) {
        detail = JSON.stringify(body.detail);
      }
    } catch {
      // Non-JSON error body: keep the status message.
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function loginRequest(
  method: 'username' | 'email',
  identifier: string,
  password: string,
): Promise<AuthToken> {
  return apiFetch<AuthToken>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ [method]: identifier, password }),
    token: null,
  });
}

export async function fetchMe(token?: string): Promise<MeResponse> {
  return apiFetch<MeResponse>('/auth/me', token !== undefined ? { token } : {});
}
