import { useEffect, useState } from 'react';
import { apiFetch } from './api';

export interface ApiState<T> {
  data: T | null;
  error: string;
}

/** Load JSON from the API once per path; exposes data and error states. */
export function useApi<T>(path: string | null): ApiState<T> {
  const [state, setState] = useState<ApiState<T>>({ data: null, error: '' });

  useEffect(() => {
    if (path === null) {
      return;
    }
    let cancelled = false;
    apiFetch<T>(path)
      .then((data) => {
        if (!cancelled) {
          setState({ data, error: '' });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            data: null,
            error: error instanceof Error ? error.message : 'Request failed',
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  return state;
}
