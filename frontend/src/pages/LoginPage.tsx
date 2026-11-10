import { FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE, apiFetch } from '../api';
import { useAuth } from '../auth/context';
import type { SignInMethod } from '../auth/context';
import LottieLoader from '../components/LottieLoader';
import type { SsoConfig } from '../types';

function dashboardPathFor(role: string): string {
  return role === 'student' ? '/schedule' : '/dashboard';
}

export default function LoginPage() {
  const { signIn, acceptToken, status, me } = useAuth();
  const navigate = useNavigate();

  const [method, setMethod] = useState<SignInMethod>('username');
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [notice, setNotice] = useState('');
  // Busy straight away when we arrive from the SSO redirect with a token
  // fragment (initial state, not a synchronous setState inside an effect).
  const [busy, setBusy] = useState(() => /access_token=/.test(window.location.hash));
  const [sso, setSso] = useState<SsoConfig | null>(null);

  // Already signed in? Leave the login screen for the role's home view.
  useEffect(() => {
    if (status === 'authenticated' && me) {
      navigate(dashboardPathFor(me.role), { replace: true });
    }
  }, [status, me, navigate]);

  // SSO redirect lands on /login#access_token=… — pick the token up.
  useEffect(() => {
    const match = /access_token=([^&]+)/.exec(window.location.hash);
    if (!match) {
      return;
    }
    window.location.hash = '';
    acceptToken(decodeURIComponent(match[1]))
      .then((profile) => navigate(dashboardPathFor(profile.role), { replace: true }))
      .catch(() => {
        setBusy(false);
        setNotice('Single sign-on session could not be restored');
      });
  }, [acceptToken, navigate]);

  useEffect(() => {
    apiFetch<SsoConfig>('/auth/sso/config')
      .then((config) => setSso(config))
      .catch(() => setSso(null));
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setNotice('');
    setBusy(true);
    try {
      const profile = await signIn(method, identifier.trim(), password);
      navigate(dashboardPathFor(profile.role), { replace: true });
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to sign in');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-shell">
      <form className="auth-card" onSubmit={handleSubmit}>
        <h1>Sign in</h1>
        <p className="hint">Use your institution username or email — both methods work for every role.</p>

        <div className="auth-tabs" role="tablist" aria-label="Sign-in method">
          <button
            type="button"
            role="tab"
            aria-selected={method === 'username'}
            className={method === 'username' ? 'tab active' : 'tab'}
            onClick={() => setMethod('username')}
          >
            Username
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={method === 'email'}
            className={method === 'email' ? 'tab active' : 'tab'}
            onClick={() => setMethod('email')}
          >
            Email
          </button>
        </div>

        <label>
          {method === 'username' ? 'Username' : 'Email'}
          <input
            aria-label={method === 'username' ? 'Username' : 'Email'}
            value={identifier}
            onChange={(event) => setIdentifier(event.target.value)}
            autoComplete={method === 'username' ? 'username' : 'email'}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            aria-label="Password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />
        </label>

        <button type="submit" disabled={busy}>
          {busy ? 'Signing in…' : 'Continue'}
        </button>

        {sso?.enabled && (
          <a className="sso-button" href={`${API_BASE}${sso.login_url}`}>
            Continue with {sso.provider} sign-on
          </a>
        )}

        {busy && <LottieLoader label="Signing you in…" />}
        {notice && (
          <p className="error-notice" role="alert">
            {notice}
          </p>
        )}
        <p className="hint">
          Demo accounts: admin / operator / faculty / student (password <code>demo-&lt;username&gt;</code>).
        </p>
      </form>
    </div>
  );
}
