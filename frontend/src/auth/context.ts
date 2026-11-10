/** Authentication session context (plain values, no components here so the
 * react-refresh rule keeps components in their own files). */
import { createContext, useContext } from 'react';
import type { MeResponse } from '../types';

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous';
export type SignInMethod = 'username' | 'email';

export interface AuthContextValue {
  status: AuthStatus;
  me: MeResponse | null;
  signIn: (method: SignInMethod, identifier: string, password: string) => Promise<MeResponse>;
  /** Persist a token handed over by the SSO redirect fragment. */
  acceptToken: (token: string) => Promise<MeResponse>;
  signOut: () => void;
}

export const AuthContext = createContext<AuthContextValue>({
  status: 'anonymous',
  me: null,
  signIn: () => Promise.reject(new Error('AuthProvider is not mounted')),
  acceptToken: () => Promise.reject(new Error('AuthProvider is not mounted')),
  signOut: () => undefined,
});

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
