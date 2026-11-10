import { Route, Routes } from 'react-router-dom';
import AuthProvider from './auth/AuthProvider';
import AppShell from './components/AppShell';
import RequireRole from './components/RequireRole';
import AdminUsersPage from './pages/AdminUsersPage';
import AiPage from './pages/AiPage';
import CampusPage from './pages/CampusPage';
import DashboardPage from './pages/DashboardPage';
import LandingPage from './pages/LandingPage';
import LoginPage from './pages/LoginPage';
import MySchedulePage from './pages/MySchedulePage';
import RoomsPage from './pages/RoomsPage';
import TimetablePage from './pages/TimetablePage';
import { STAFF_ROLES } from './types';

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />

        {/* Authenticated shell: every route below requires a session and is
            rendered inside the role-aware navigation. */}
        <Route element={<RequireRole><AppShell /></RequireRole>}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/schedule" element={<MySchedulePage />} />
          <Route path="/campus" element={<CampusPage />} />
          <Route path="/ai" element={<AiPage />} />
          <Route
            path="/timetable"
            element={<RequireRole allow={STAFF_ROLES}><TimetablePage /></RequireRole>}
          />
          <Route
            path="/rooms"
            element={<RequireRole allow={STAFF_ROLES}><RoomsPage /></RequireRole>}
          />
          <Route
            path="/admin/users"
            element={<RequireRole allow={['administrator']}><AdminUsersPage /></RequireRole>}
          />
        </Route>

        <Route path="*" element={<LandingPage />} />
      </Routes>
    </AuthProvider>
  );
}
