import { FormEvent, useState } from 'react';

export default function LoginPage() {
  const [email, setEmail] = useState('admin@northbridge.edu');
  const [password, setPassword] = useState('demo-admin');
  const [notice, setNotice] = useState('');

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const response = await fetch('http://localhost:8000/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await response.json();

    if (!response.ok) {
      setNotice(data.detail || 'Unable to sign in');
      return;
    }

    setNotice(`Logged in as ${data.role} for institution ${data.institution_id}`);
  }

  return (
    <div className="auth-shell">
      <form className="auth-card" onSubmit={handleSubmit}>
        <h1>Sign in</h1>
        <label>
          Email
          <input value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        <button type="submit">Continue</button>
        <p className="hint">Demo credentials are seeded for the default institution.</p>
        {notice && <p>{notice}</p>}
      </form>
    </div>
  );
}
