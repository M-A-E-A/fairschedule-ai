import { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/context';
import type { Role } from '../types';
import LottieLoader from './LottieLoader';

/**
 * Route guard: anonymous visitors go to /login, authenticated users outside
 * `allow` are bounced to a view they may use. Enforcement mirrors the
 * backend's role checks — the UI hides what the API would refuse anyway.
 */
export default function RequireRole({
  children,
  allow,
}: {
  children: ReactNode;
  allow?: Role[];
}) {
  const { status, me } = useAuth();
  const location = useLocation();

  if (status === 'loading') {
    return (
      <div className="guard-state" role="status">
        <LottieLoader label="Checking your session…" />
      </div>
    );
  }

  if (status === 'anonymous' || me === null) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (allow && !allow.includes(me.role)) {
    return <Navigate to={me.role === 'student' ? '/schedule' : '/dashboard'} replace />;
  }

  return <>{children}</>;
}
