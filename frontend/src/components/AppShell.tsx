import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/context';
import { ROOM_MANAGER_ROLES, STAFF_ROLES } from '../types';
import type { Role } from '../types';

interface NavItem {
  to: string;
  label: string;
  allow?: Role[];
}

/** Role-aware primary navigation: students never see staff/admin entries. */
const NAV_ITEMS: NavItem[] = [
  { to: '/dashboard', label: 'Overview' },
  { to: '/schedule', label: 'My schedule' },
  { to: '/campus', label: '3D campus' },
  { to: '/timetable', label: 'Timetable', allow: STAFF_ROLES },
  { to: '/rooms', label: 'Rooms', allow: STAFF_ROLES },
  { to: '/admin/users', label: 'Users', allow: ['administrator'] },
  { to: '/ai', label: 'AI assistant' },
];

export default function AppShell() {
  const { me, signOut } = useAuth();
  const navigate = useNavigate();

  if (!me) {
    return null;
  }

  const visibleItems = NAV_ITEMS.filter((item) => !item.allow || item.allow.includes(me.role));
  const canManageRooms = ROOM_MANAGER_ROLES.includes(me.role);

  function handleSignOut() {
    signOut();
    navigate('/login', { replace: true });
  }

  return (
    <div className="dashboard-shell">
      <aside className="sidebar">
        <h2>FairSchedule AI</h2>
        <p className="tenant-name">{me.institution_name}</p>
        <nav aria-label="Main navigation">
          <ul>
            {visibleItems.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} className={({ isActive }) => (isActive ? 'active' : undefined)}>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="sidebar-footer">
          <span className="role-badge" data-testid="role-badge">
            {me.role.replace('_', ' ')}
          </span>
          <span className="signed-in-as" title={me.email}>
            {me.full_name || me.username}
          </span>
          <button type="button" className="sign-out" onClick={handleSignOut}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="dashboard-content">
        <Outlet context={{ me, canManageRooms }} />
      </main>
    </div>
  );
}
