import { ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { TOKEN_KEY, fetchMe, loginRequest } from '../api';
import type { MeResponse } from '../types';
import { AuthContext } from './context';
import type { AuthStatus, SignInMethod } from './context';

/**
 * Owns the session: restores a stored token on startup, signs in with either
 * username or email, accepts SSO callback tokens, and clears on sign-out.
 */
export default function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>(() =>
    localStorage.getItem(TOKEN_KEY) ? 'loading' : 'anonymous',
  );
  const [me, setMe] = useState<MeResponse | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
    if (!stored) {
      // Initial state is already 'anonymous' when no token was stored.
      return;
    }
    let cancelled = false;
    fetchMe(stored)
      .then((profile) => {
        if (!cancelled) {
          setMe(profile);
          setStatus('authenticated');
        }
      })
      .catch(() => {
        if (!cancelled) {
          localStorage.removeItem(TOKEN_KEY);
          setMe(null);
          setStatus('anonymous');
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(
    async (method: SignInMethod, identifier: string, password: string): Promise<MeResponse> => {
      const auth = await loginRequest(method, identifier, password);
      localStorage.setItem(TOKEN_KEY, auth.access_token);
      const profile = await fetchMe(auth.access_token);
      setMe(profile);
      setStatus('authenticated');
      return profile;
    },
    [],
  );

  const acceptToken = useCallback(async (token: string): Promise<MeResponse> => {
    const profile = await fetchMe(token);
    localStorage.setItem(TOKEN_KEY, token);
    setMe(profile);
    setStatus('authenticated');
    return profile;
  }, []);

  const signOut = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setMe(null);
    setStatus('anonymous');
  }, []);

  const value = useMemo(
    () => ({ status, me, signIn, acceptToken, signOut }),
    [status, me, signIn, acceptToken, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
