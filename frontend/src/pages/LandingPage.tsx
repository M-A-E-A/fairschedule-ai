import { useEffect, useRef } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

export default function LandingPage() {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from('.reveal', {
        opacity: 0,
        y: 36,
        duration: 0.8,
        stagger: 0.12,
        ease: 'power2.out',
        scrollTrigger: {
          trigger: '.reveal',
          start: 'top 85%',
        },
      });
    }, containerRef);

    return () => ctx.revert();
  }, []);

  return (
    <div className="landing-page" ref={containerRef}>
      <header className="topbar">
        <div className="brand">FairSchedule AI</div>
        <nav className="navlinks">
          <a href="#features">Features</a>
          <a href="#workflow">How it works</a>
          <a href="#demo">Demo</a>
        </nav>
        <a className="nav-button" href="/login">Try the demo</a>
      </header>

      <main>
        <section className="hero section">
          <div className="hero-copy reveal">
            <p className="eyebrow">Smarter planning for every campus</p>
            <h1>Plan fair, conflict-free schedules without spreadsheet chaos.</h1>
            <p className="lede">FairSchedule AI helps institutions manage rooms, lecturers, cohorts, and timetable repairs with transparent optimization and tenant-aware controls.</p>
            <div className="cta-row">
              <a className="action-button primary" href="/login">Try the demo</a>
              <a className="action-button secondary" href="#features">Explore features</a>
            </div>
          </div>

          <div className="preview-panel reveal">
            <div className="mini-grid">
              <span>Mon</span>
              <span>Tue</span>
              <span>Wed</span>
              <span>Thu</span>
              <span>Fri</span>
            </div>
            <div className="mini-schedule">
              <div className="mini-block block-a">CS101</div>
              <div className="mini-block block-b">Lab</div>
              <div className="mini-block block-c">DBS</div>
              <div className="mini-block block-d">Free</div>
            </div>
          </div>
        </section>

        <section id="features" className="section reveal">
          <h2>Built for the realities of university scheduling</h2>
          <div className="feature-grid">
            <article className="feature-card">
              <h3>Conflict-free planning</h3>
              <p>Room, lecturer, and cohort clashes are checked before the timetable is approved.</p>
            </article>
            <article className="feature-card">
              <h3>AI-assisted review</h3>
              <p>Questions and change proposals stay grounded in the institution’s approved data.</p>
            </article>
            <article className="feature-card">
              <h3>Fairness-aware optimization</h3>
              <p>Weight adjustments help reduce poor slot distribution without hiding hard constraints.</p>
            </article>
            <article className="feature-card">
              <h3>Campus visibility</h3>
              <p>Students and staff can view room status in a 3D campus view and a plain list view.</p>
            </article>
          </div>
        </section>

        <section id="workflow" className="section reveal">
          <h2>How it works</h2>
          <div className="steps-grid">
            <div className="step-box"><span>1</span><p>Import and validate</p></div>
            <div className="step-box"><span>2</span><p>Generate a draft</p></div>
            <div className="step-box"><span>3</span><p>Review and repair</p></div>
            <div className="step-box"><span>4</span><p>Publish</p></div>
          </div>
        </section>

        <section id="demo" className="section final-cta reveal">
          <h2>Ready to see the demo flow?</h2>
          <a className="action-button primary" href="/login">Explore the demo</a>
        </section>
      </main>
    </div>
  );
}
