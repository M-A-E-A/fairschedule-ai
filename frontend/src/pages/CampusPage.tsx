import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { Canvas } from '@react-three/fiber';
import LottieLoader from '../components/LottieLoader';
import type { Campus, MeResponse, Room } from '../types';
import { useApi } from '../useApi';

/**
 * Data-driven 3D campus: one building per room of the selected campus, sized
 * by capacity, plus a plain list view of the same rooms.
 */
export function CampusCanvas({ rooms }: { rooms: Room[] }) {
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
        const palette = ['#7dd3fc', '#a78bfa', '#34d399', '#f59e0b'];
        return (
          <mesh key={room.id} position={[(column - 1.5) * 2.4, height / 2, (row - 1) * 2.4]}>
            <boxGeometry args={[1.6, height, 1.6]} />
            <meshStandardMaterial color={palette[index % palette.length]} />
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
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const { data: rooms, error: roomError } = useApi<Room[]>(`/institutions/${me.institution_id}/rooms`);

  const error = campusError || roomError;
  if (error) {
    return <p className="error-notice" role="alert">{error}</p>;
  }
  if (!campuses) {
    return <LottieLoader label="Loading campus…" />;
  }

  const activeCampus = campuses.find((campus) => campus.id === selectedId) ?? campuses[0];
  const visibleRooms = (rooms ?? []).filter((room) => room.campus_id === activeCampus?.id);

  return (
    <>
      <header className="dashboard-header">
        <div>
          <h1>3D campus</h1>
          <p className="hint">
            {activeCampus?.name} · {visibleRooms.length} building(s) shown, sized by capacity
          </p>
        </div>
        <label className="campus-select">
          Campus
          <select
            aria-label="Select campus"
            value={activeCampus?.id ?? ''}
            onChange={(event) => setSelectedId(Number(event.target.value))}
          >
            {campuses.map((campus) => (
              <option key={campus.id} value={campus.id}>
                {campus.name}
              </option>
            ))}
          </select>
        </label>
      </header>

      <section className="panel campus-panel">
        <div className="campus-view">
          {rooms === null ? <LottieLoader label="Loading buildings…" /> : <CampusCanvas rooms={visibleRooms} />}
        </div>
        <ul className="room-legend">
          {visibleRooms.map((room) => (
            <li key={room.id}>
              <strong>{room.name}</strong> — {room.room_type}, {room.capacity} seats
            </li>
          ))}
          {visibleRooms.length === 0 && <li className="empty-state">No rooms on this campus yet.</li>}
        </ul>
      </section>
    </>
  );
}
