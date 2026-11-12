/** Shared API response types mirroring the backend schemas. */

export type Role = 'administrator' | 'campus_operator' | 'faculty' | 'student';

/** Roles that may plan schedules and read the full timetable. */
export const STAFF_ROLES: Role[] = ['administrator', 'campus_operator', 'faculty'];
/** Roles that may allocate rooms (mirrors backend ROOM_MANAGERS). */
export const ROOM_MANAGER_ROLES: Role[] = ['administrator', 'campus_operator'];
/** Roles that may approve proposals and publish timetables (mirrors backend PROPOSAL_APPROVERS). */
export const PROPOSAL_APPROVER_ROLES: Role[] = ['administrator', 'campus_operator'];

export interface AuthToken {
  access_token: string;
  token_type: string;
  role: Role;
  institution_id: number;
  username: string;
  full_name: string;
}

export interface MeResponse {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: Role;
  institution_id: number;
  institution_name: string;
  student_group_id: number | null;
  lecturer_id: number | null;
}

export interface SsoConfig {
  enabled: boolean;
  provider: string;
  login_url: string;
  client_id: string;
  redirect_uri: string;
}

export interface OverviewResponse {
  institution_id: number;
  institution_name: string;
  campuses: number;
  rooms: number;
  courses: number;
  lecturers: number;
  student_groups: number;
  sessions: number;
  published_sessions: number;
  pending_proposals: number;
  role: Role;
}

export interface ScheduleSession {
  id: number;
  campus_id: number;
  course_id: number;
  course_code: string;
  course_name: string;
  lecturer_id: number;
  lecturer_name: string;
  student_group_id: number;
  student_group_name: string;
  room_id: number;
  room_name: string;
  day: number;
  day_name: string;
  start_minute: number;
  start_time: string;
  end_minute: number;
  end_time: string;
  duration_minute: number;
  status: string;
}

export interface ScheduleResponse {
  role: Role;
  scope: 'student' | 'lecturer' | 'institution';
  sessions: ScheduleSession[];
}

export interface TimetableResponse {
  institution_id: number;
  sessions: ScheduleSession[];
}

/** One published timetable version (GET /institutions/:id/timetable/versions). */
export interface TimetableVersionEntry {
  id: number;
  version: number;
  label: string;
  published_by_email: string;
  published_at: string;
  session_count: number;
}

/** A booking row frozen inside a published version / diff (fields only). */
export interface BookingSnapshotRow {
  id: number;
  campus_id: number;
  course_id: number;
  lecturer_id: number;
  student_group_id: number;
  room_id: number;
  day: number;
  start_minute: number;
  duration_minute: number;
  status: string;
}

export interface TimetableDiffResponse {
  institution_id: number;
  published_version: number | null;
  published_label: string | null;
  draft_session_count: number;
  added: BookingSnapshotRow[];
  removed: BookingSnapshotRow[];
  moved: { id: number; from: BookingSnapshotRow; to: BookingSnapshotRow }[];
}

/** One admin-only audit event (GET /audit-events), newest first by id. */
export interface AuditEvent {
  id: number;
  user_email: string;
  event_type: string;
  message: string;
}

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: Role;
  institution_id: number;
  is_active: boolean;
  student_group_id: number | null;
  lecturer_id: number | null;
  sso_linked: boolean;
}

export interface Room {
  id: number;
  institution_id: number;
  campus_id: number;
  name: string;
  capacity: number;
  room_type: string;
  equipment: string;
}

/** A session booking row (GET /institutions/:id/bookings). */
export interface Booking {
  id: number;
  institution_id: number;
  campus_id: number;
  course_id: number;
  lecturer_id: number;
  student_group_id: number;
  room_id: number;
  day: number;
  start_minute: number;
  duration_minute: number;
  status: string;
}

export interface Campus {
  id: number;
  name: string;
  slug: string;
  width: number;
  depth: number;
  room_count: number;
}

export interface Course {
  id: number;
  code: string;
  name: string;
  required_room_type: string;
}

export interface Lecturer {
  id: number;
  name: string;
  email: string;
}

export interface StudentGroup {
  id: number;
  name: string;
  size: number;
}
