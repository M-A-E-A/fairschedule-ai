import { FormEvent, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { apiFetch } from '../api';
import LottieLoader from '../components/LottieLoader';
import type { Campus, MeResponse, Room } from '../types';
import { useApi } from '../useApi';

export default function RoomsPage() {
  const { me, canManageRooms } = useOutletContext<{ me: MeResponse; canManageRooms: boolean }>();
  const { data, error } = useApi<Room[]>(`/institutions/${me.institution_id}/rooms`);
  const { data: campuses } = useApi<Campus[]>(`/institutions/${me.institution_id}/campuses`);
  const [rooms, setRooms] = useState<Room[] | null>(null);
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);

  const list = rooms ?? data;

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = {
      campus_id: Number(new FormData(form).get('campus_id')),
      name: String(new FormData(form).get('name')),
      capacity: Number(new FormData(form).get('capacity')),
      room_type: String(new FormData(form).get('room_type') || 'lecture'),
      equipment: String(new FormData(form).get('equipment') || ''),
    };
    setSaving(true);
    setNotice('');
    try {
      const created = await apiFetch<Room>(`/institutions/${me.institution_id}/rooms`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setRooms([...(list ?? []), created]);
      form.reset();
    } catch (createError) {
      setNotice(createError instanceof Error ? createError.message : 'Could not create the room');
    } finally {
      setSaving(false);
    }
  }

  if (error) {
    return <p className="error-notice" role="alert">{error}</p>;
  }
  if (!list) {
    return <LottieLoader label="Loading rooms…" />;
  }

  return (
    <>
      <header className="dashboard-header">
        <div>
          <h1>Rooms</h1>
          <p className="hint">{list.length} room(s) · {me.institution_name}</p>
        </div>
      </header>

      {notice && <p className="error-notice" role="alert">{notice}</p>}

      {canManageRooms && campuses && (
        <section className="panel create-form">
          <h3>Add a room</h3>
          <form onSubmit={handleCreate}>
            <label>
              Campus
              <select name="campus_id" defaultValue={String(campuses[0]?.id ?? '')} aria-label="Campus">
                {campuses.map((campus) => (
                  <option key={campus.id} value={campus.id}>
                    {campus.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Name
              <input name="name" required aria-label="Room name" />
            </label>
            <label>
              Capacity
              <input name="capacity" type="number" min={1} required aria-label="Capacity" />
            </label>
            <label>
              Type
              <select name="room_type" defaultValue="lecture" aria-label="Room type">
                <option value="lecture">lecture</option>
                <option value="lab">lab</option>
                <option value="seminar">seminar</option>
              </select>
            </label>
            <label>
              Equipment
              <input name="equipment" aria-label="Equipment" />
            </label>
            <button type="submit" disabled={saving}>
              {saving ? 'Adding…' : 'Add room'}
            </button>
          </form>
        </section>
      )}

      <section className="panel">
        <table>
          <thead>
            <tr>
              <th>Room</th>
              <th>Campus</th>
              <th>Capacity</th>
              <th>Type</th>
              <th>Equipment</th>
            </tr>
          </thead>
          <tbody>
            {list.map((room) => (
              <tr key={room.id}>
                <td>{room.name}</td>
                <td>{campuses?.find((campus) => campus.id === room.campus_id)?.name ?? room.campus_id}</td>
                <td>{room.capacity}</td>
                <td>{room.room_type}</td>
                <td>{room.equipment || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
