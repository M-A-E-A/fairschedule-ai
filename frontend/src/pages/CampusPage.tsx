import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { Canvas } from '@react-three/fiber';
import LottieLoader from '../components/LottieLoader';
import type { Booking, Campus, Course, Lecturer, MeResponse, Room, StudentGroup } from '../types';
import { useApi } from '../useApi';

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

/** Scene colours for the selected time window (mirrored by the legend). */
export const OCCUPIED_COLOR = '#f87171';
export const FREE_COLOR = '#34d399';

/**
 * Rooms with a session covering (day, minute) — start inclusive, end
 * exclusive. Pure so the occupancy boundary semantics are testable directly.
 */
export function occupiedRoomIds(bookings: Booking[], day: number, minute: number): Set<number> {
  const occupied = new Set<number>();
  for (const booking of bookings) {
    const covers =
      booking.day === day &&
      booking.start_minute <= minute &&
      minute < booking.start_minute + booking.duration_minute;
    if (covers) {
      occupied.add(booking.room_id);
    }
  }
  return occupied;
}

/** 'HH:MM' → minutes since midnight; anything unparsable reads as midnight. */
export function timeToMinute(value: string): number {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  if (match === null) {
    return 0;
  }
  return Number(match[1]) * 60 + Number(match[2]);
}

/** Minutes since midnight → 'HH:MM'. */
export function minuteToTime(minute: number): string {
  const hours = Math.floor(minute / 60);
  const minutes = minute % 60;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
}

/**
 * The 3D scene: one building per room of the selected campus, sized by
 * capacity, coloured by occupancy for the selected day/time window. Clicking
 * a building selects that room's schedule.
 */
export function CampusCanvas({
  rooms,
  occupied,
  onSelectRoom,
}: {
  rooms: Room[];
  occupied: Set<number>;
  onSelectRoom: (roomId: number) => void;
}) {
  return (
    <Canvas camera={{ position: [0, 6, 10], fov: 45 }} aria-label="3D campus view">
      <ambientLight intensity={1.1} />
      <directionalLight position={[6, 8, 4]} />
      <mesh position={[0, -0.25, 0]}>
        <boxGeometry args={[12, 0.4, 8]} />
        <meshStandardMaterial color="#1e293b" />
      </mesh>
      {rooms.map((room, index) => {
        const column = index % 4;
        const row = Math.floor(index / 4);
        const height = Math.max(1, Math.min(4, room.capacity / 30));
        return (
          <mesh
            key={room.id}
            name={room.name}
            position={[(column - 1.5) * 2.4, height / 2, (row - 1) * 2.4]}
            onClick={() => onSelectRoom(room.id)}
          >
            <boxGeometry args={[1.6, height, 1.6]} />
            <meshStandardMaterial color={occupied.has(room.id) ? OCCUPIED_COLOR : FREE_COLOR} />
          </mesh>
        );
      })}
    </Canvas>
  );
}

export default function CampusPage() {
  const { me } = useOutletContext<{ me: MeResponse }>();
  const { data: campuses, error: campusError } = useApi<Campus[]>(
    `/institutions/${me.institution_id}/campuses`,
  );
  const { data: rooms, error: roomError } = useApi<Room[]>(`/institutions/${me.institution_id}/rooms`);
  // Occupancy and the room schedules come from the existing bookings endpoint
  // (role-scoped: students see their own cohort's sessions there). Course,
  // lecturer, and student-group lists are the same tenant-scoped lookups the
  // rest of the app uses, only for labels.
  const { data: bookings, error: bookingError } = useApi<Booking[]>(
    `/institutions/${me.institution_id}/bookings`,
  );
  const { data: courses } = useApi<Course[]>(`/institutions/${me.institution_id}/courses`);
  const { data: lecturers } = useApi<Lecturer[]>(`/institutions/${me.institution_id}/lecturers`);
  const { data: studentGroups } = useApi<StudentGroup[]>(
    `/institutions/${me.institution_id}/student-groups`,
  );

  const [selectedCampusId, setSelectedCampusId] = useState<number | null>(null);
  const [day, setDay] = useState(0);
  const [time, setTime] = useState('09:00');
  const [selectedRoomId, setSelectedRoomId] = useState<number | null>(null);

  const error = campusError || roomError || bookingError;
  if (error) {
    return <p className="error-notice" role="alert">{error}</p>;
  }
  if (!campuses || !bookings) {
    return <LottieLoader label="Loading campus…" />;
  }

  const activeCampus = campuses.find((campus) => campus.id === selectedCampusId) ?? campuses[0];
  const visibleRooms = (rooms ?? []).filter((room) => room.campus_id === activeCampus?.id);
  const occupied = occupiedRoomIds(bookings, day, timeToMinute(time));
  const selectedRoom = visibleRooms.find((room) => room.id === selectedRoomId) ?? null;
  const roomSessions = selectedRoom
    ? bookings
        .filter((booking) => booking.room_id === selectedRoom.id && booking.day === day)
        .sort((a, b) => a.start_minute - b.start_minute)
    : [];

  const courseLabel = (courseId: number) => {
    const course = (courses ?? []).find((item) => item.id === courseId);
    return course ? `${course.code} · ${course.name}` : `Course #${courseId}`;
  };
  const lecturerLabel = (lecturerId: number) => {
    const lecturer = (lecturers ?? []).find((item) => item.id === lecturerId);
    return lecturer ? lecturer.name : `Lecturer #${lecturerId}`;
  };
  const groupLabel = (groupId: number) => {
    const group = (studentGroups ?? []).find((item) => item.id === groupId);
    return group ? group.name : `Group #${groupId}`;
  };

  function selectRoom(roomId: number) {
    setSelectedRoomId(roomId);
  }

  return (
    <>
      <header className="dashboard-header">
        <div>
          <h1>3D campus</h1>
          <p className="hint">
            {activeCampus?.name} · {visibleRooms.length} building(s) · occupancy on {DAY_NAMES[day]} at {time}
          </p>
          {me.role === 'student' && (
            <p className="hint">Occupancy reflects your cohort's sessions.</p>
          )}
        </div>
        <div className="campus-controls">
          <label className="campus-select">
            Campus
            <select
              aria-label="Select campus"
              value={activeCampus?.id ?? ''}
              onChange={(event) => setSelectedCampusId(Number(event.target.value))}
            >
              {campuses.map((campus) => (
                <option key={campus.id} value={campus.id}>
                  {campus.name}
                </option>
              ))}
            </select>
          </label>
          <label className="campus-select">
            Day
            <select
              aria-label="Select day"
              value={day}
              onChange={(event) => setDay(Number(event.target.value))}
            >
              {DAY_NAMES.map((name, index) => (
                <option key={name} value={index}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="campus-select">
            Time
            <input
              type="time"
              aria-label="Select time"
              value={time}
              onChange={(event) => setTime(event.target.value)}
            />
          </label>
        </div>
      </header>

      <section className="panel campus-panel">
        <div className="campus-view">
          {rooms === null ? (
            <LottieLoader label="Loading buildings…" />
          ) : (
            <CampusCanvas rooms={visibleRooms} occupied={occupied} onSelectRoom={selectRoom} />
          )}
        </div>
        <ul className="room-legend">
          {visibleRooms.map((room) => {
            const isOccupied = occupied.has(room.id);
            return (
              <li key={room.id}>
                <button
                  type="button"
                  className={`room-toggle ${isOccupied ? 'room-occupied' : 'room-free'}`}
                  aria-pressed={selectedRoomId === room.id}
                  onClick={() => selectRoom(room.id)}
                >
                  <strong>{room.name}</strong> — {room.room_type}, {room.capacity} seats ·{' '}
                  {isOccupied ? 'occupied' : 'free'}
                </button>
              </li>
            );
          })}
          {visibleRooms.length === 0 && <li className="empty-state">No rooms on this campus yet.</li>}
        </ul>
      </section>

      {selectedRoom && (
        <section className="panel room-schedule" aria-label={`${selectedRoom.name} schedule`}>
          <h2>
            {selectedRoom.name} · {DAY_NAMES[day]}
          </h2>
          {roomSessions.length === 0 ? (
            <p className="empty-state">
              No sessions in {selectedRoom.name} on {DAY_NAMES[day]}.
            </p>
          ) : (
            <ul className="session-list">
              {roomSessions.map((booking) => (
                <li className="session-card" key={booking.id} data-testid={`booking-${booking.id}`}>
                  <div className="session-time">
                    <strong>{minuteToTime(booking.start_minute)}</strong>
                    <span>–{minuteToTime(booking.start_minute + booking.duration_minute)}</span>
                  </div>
                  <div className="session-body">
                    <span className="session-course">{courseLabel(booking.course_id)}</span>
                    <span className="session-meta">
                      {lecturerLabel(booking.lecturer_id)} · {groupLabel(booking.student_group_id)}
                    </span>
                  </div>
                  <span className={`status-badge status-${booking.status}`}>{booking.status}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </>
  );
}
