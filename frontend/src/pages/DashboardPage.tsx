import { Canvas } from '@react-three/fiber';

function Campus3D() {
  return (
    <Canvas camera={{ position: [0, 4, 8], fov: 45 }}>
      <ambientLight intensity={1.2} />
      <directionalLight position={[3, 5, 3]} />
      <mesh position={[0, 0, 0]}>
        <boxGeometry args={[3.5, 1, 3.5]} />
        <meshStandardMaterial color="#7dd3fc" />
      </mesh>
      <mesh position={[-2.2, 1.2, 0.5]}>
        <boxGeometry args={[1.2, 2.2, 1.2]} />
        <meshStandardMaterial color="#a78bfa" />
      </mesh>
      <mesh position={[2.2, 1.1, -0.6]}>
        <boxGeometry args={[1.5, 2, 1.5]} />
        <meshStandardMaterial color="#34d399" />
      </mesh>
    </Canvas>
  );
}

export default function DashboardPage() {
  return (
    <div className="dashboard-shell">
      <aside className="sidebar">
        <h2>FairSchedule AI</h2>
        <ul>
          <li>Overview</li>
          <li>Timetable</li>
          <li>Rooms</li>
          <li>AI assistant</li>
        </ul>
      </aside>

      <main className="dashboard-content">
        <header className="dashboard-header">
          <h1>Institution overview</h1>
          <button>Generate schedule</button>
        </header>

        <div className="stats-grid">
          <div className="stat-card"><span>Campuses</span><strong>2</strong></div>
          <div className="stat-card"><span>Rooms</span><strong>5</strong></div>
          <div className="stat-card"><span>Courses</span><strong>7</strong></div>
          <div className="stat-card"><span>Sessions</span><strong>42</strong></div>
        </div>

        <div className="panel-grid">
          <section className="panel">
            <h3>Weekly timetable</h3>
            <table>
              <thead>
                <tr><th>Course</th><th>Day</th><th>Time</th><th>Room</th></tr>
              </thead>
              <tbody>
                <tr><td>CS101</td><td>Mon</td><td>09:00</td><td>A101</td></tr>
                <tr><td>DBS201</td><td>Tue</td><td>10:00</td><td>C315</td></tr>
              </tbody>
            </table>
          </section>

          <section className="panel campus-panel">
            <h3>Campus overview</h3>
            <div className="campus-view">
              <Campus3D />
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
