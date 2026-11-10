import { FormEvent, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { apiFetch } from '../api';
import LottieLoader from '../components/LottieLoader';
import type { AdminUser, MeResponse, Role } from '../types';
import { useApi } from '../useApi';

const ROLE_OPTIONS: Role[] = ['administrator', 'campus_operator', 'faculty', 'student'];

export default function AdminUsersPage() {
  const { me } = useOutletContext<{ me: MeResponse }>();
  const { data, error } = useApi<AdminUser[]>('/admin/users');
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);

  const list = users ?? data;

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setSaving(true);
    setNotice('');
    try {
      const created = await apiFetch<AdminUser>('/admin/users', {
        method: 'POST',
        body: JSON.stringify({
          username: String(fields.get('username')),
          email: String(fields.get('email')),
          password: String(fields.get('password')),
          full_name: String(fields.get('full_name') ?? ''),
          role: String(fields.get('role')),
        }),
      });
      setUsers([...(list ?? []), created]);
      form.reset();
      setNotice(`Created ${created.username} (${created.role.replace('_', ' ')})`);
    } catch (createError) {
      setNotice(createError instanceof Error ? createError.message : 'Could not create the user');
    } finally {
      setSaving(false);
    }
  }

  if (error) {
    return <p className="error-notice" role="alert">{error}</p>;
  }
  if (!list) {
    return <LottieLoader label="Loading users…" />;
  }

  return (
    <>
      <header className="dashboard-header">
        <div>
          <h1>Users</h1>
          <p className="hint">Accounts in {me.institution_name} only — other tenants are never listed</p>
        </div>
      </header>

      {notice && <p className="notice" role="status">{notice}</p>}

      <section className="panel create-form">
        <h3>Create a user</h3>
        <form onSubmit={handleCreate}>
          <label>
            Username
            <input name="username" required pattern="[A-Za-z0-9._-]{3,64}" aria-label="Username" />
          </label>
          <label>
            Email
            <input name="email" type="email" required aria-label="Email" />
          </label>
          <label>
            Full name
            <input name="full_name" aria-label="Full name" />
          </label>
          <label>
            Password
            <input name="password" type="password" minLength={8} required aria-label="Password" />
          </label>
          <label>
            Role
            <select name="role" defaultValue="student" aria-label="Role">
              {ROLE_OPTIONS.map((role) => (
                <option key={role} value={role}>
                  {role.replace('_', ' ')}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={saving}>
            {saving ? 'Creating…' : 'Create user'}
          </button>
        </form>
      </section>

      <section className="panel">
        <table>
          <thead>
            <tr>
              <th>Username</th>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              <th>Sign-in</th>
            </tr>
          </thead>
          <tbody>
            {list.map((user) => (
              <tr key={user.id}>
                <td>{user.username}</td>
                <td>{user.full_name || '—'}</td>
                <td>{user.email}</td>
                <td>
                  <span className="role-badge">{user.role.replace('_', ' ')}</span>
                </td>
                <td>{user.is_active ? 'active' : 'disabled'}</td>
                <td>{user.sso_linked ? 'SSO + password' : 'password'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
