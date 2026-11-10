"""Deterministic demo seed data for two independent tenants.

The seed only runs when the database has no users at all, so it never
overwrites data created during a running session.
"""

from __future__ import annotations

from sqlmodel import Session, delete, select

from app.core.security import hash_password
from app.models import (
    AuditEvent,
    Building,
    Campus,
    Course,
    Department,
    Institution,
    Lecturer,
    Room,
    ScheduleProposal,
    SessionBooking,
    StudentGroup,
    User,
)

# Child tables first so foreign keys stay satisfied under PostgreSQL.
_SEED_MODELS = [
    AuditEvent,
    ScheduleProposal,
    SessionBooking,
    User,
    StudentGroup,
    Lecturer,
    Course,
    Room,
    Building,
    Department,
    Campus,
    Institution,
]


def seed_demo_data(engine) -> None:
    with Session(engine) as session:
        if session.exec(select(User)).first() is not None:
            return

        for model in _SEED_MODELS:
            session.exec(delete(model))
        session.commit()

        northbridge = Institution(name='Northbridge University', slug='northbridge', tenant_code='NBU')
        harbor = Institution(name='Harbor College', slug='harbor', tenant_code='HRC')
        session.add_all([northbridge, harbor])
        session.commit()
        session.refresh(northbridge)
        session.refresh(harbor)

        main_campus = Campus(name='Main Campus', slug='main', institution_id=northbridge.id, width=60, depth=40)
        tech_campus = Campus(name='Tech Park', slug='tech-park', institution_id=northbridge.id, width=40, depth=30)
        harbor_campus = Campus(name='Harbor South', slug='harbor-south', institution_id=harbor.id, width=50, depth=35)
        session.add_all([main_campus, tech_campus, harbor_campus])
        session.commit()

        room_a101 = Room(
            institution_id=northbridge.id, campus_id=main_campus.id, name='A101',
            capacity=80, room_type='lecture', equipment='projector',
        )
        room_b204 = Room(
            institution_id=northbridge.id, campus_id=main_campus.id, name='B204',
            capacity=40, room_type='lab', equipment='computers',
        )
        room_c315 = Room(
            institution_id=northbridge.id, campus_id=main_campus.id, name='C315',
            capacity=120, room_type='lecture', equipment='projector,screen',
        )
        room_t12 = Room(
            institution_id=northbridge.id, campus_id=tech_campus.id, name='T12',
            capacity=65, room_type='seminar', equipment='whiteboard',
        )
        room_h1 = Room(
            institution_id=harbor.id, campus_id=harbor_campus.id, name='H1',
            capacity=70, room_type='lecture', equipment='projector',
        )
        session.add_all([room_a101, room_b204, room_c315, room_t12, room_h1])
        session.commit()

        course_cs101 = Course(
            institution_id=northbridge.id, code='CS101', name='Intro to Computing', required_room_type='any'
        )
        course_dbs201 = Course(
            institution_id=northbridge.id, code='DBS201', name='Database Systems', required_room_type='lab'
        )
        course_mth120 = Course(
            institution_id=northbridge.id, code='MTH120', name='Discrete Mathematics', required_room_type='any'
        )
        course_eng110 = Course(
            institution_id=harbor.id, code='ENG110', name='Engineering Foundations', required_room_type='any'
        )
        session.add_all([course_cs101, course_dbs201, course_mth120, course_eng110])
        session.commit()

        lecturer_ada = Lecturer(institution_id=northbridge.id, name='Ada Reed', email='ada@northbridge.edu')
        lecturer_sam = Lecturer(institution_id=northbridge.id, name='Sam Chen', email='sam@northbridge.edu')
        lecturer_priya = Lecturer(institution_id=northbridge.id, name='Priya Nair', email='priya@northbridge.edu')
        lecturer_milo = Lecturer(institution_id=harbor.id, name='Milo Stone', email='milo@harbor.edu')
        session.add_all([lecturer_ada, lecturer_sam, lecturer_priya, lecturer_milo])
        session.commit()

        group_cs1 = StudentGroup(institution_id=northbridge.id, name='CS Year 1', size=35)
        group_cs2 = StudentGroup(institution_id=northbridge.id, name='CS Year 2', size=40)
        group_eng = StudentGroup(institution_id=harbor.id, name='Engineering Cohort', size=60)
        session.add_all([group_cs1, group_cs2, group_eng])
        session.commit()

        users = [
            User(
                username='admin', email='admin@northbridge.edu', password_hash=hash_password('demo-admin'),
                full_name='Alice Admin', role='administrator', institution_id=northbridge.id,
            ),
            User(
                username='operator', email='operator@northbridge.edu', password_hash=hash_password('demo-operator'),
                full_name='Omar Operator', role='campus_operator', institution_id=northbridge.id,
            ),
            User(
                username='faculty', email='faculty@northbridge.edu', password_hash=hash_password('demo-faculty'),
                full_name='Ada Reed', role='faculty', institution_id=northbridge.id, lecturer_id=lecturer_ada.id,
            ),
            User(
                username='student', email='student@northbridge.edu', password_hash=hash_password('demo-student'),
                full_name='Sara Student', role='student', institution_id=northbridge.id,
                student_group_id=group_cs1.id,
            ),
            User(
                username='harbor-admin', email='admin@harbor.edu',
                password_hash=hash_password('demo-admin-harbor'), full_name='Hannah Harbor',
                role='administrator', institution_id=harbor.id,
            ),
        ]
        session.add_all(users)
        session.commit()

        bookings = [
            # Northbridge: CS101 (any room) in the 80-seat lecture hall.
            SessionBooking(
                institution_id=northbridge.id, campus_id=main_campus.id, course_id=course_cs101.id,
                lecturer_id=lecturer_ada.id, student_group_id=group_cs1.id, room_id=room_a101.id,
                day=0, start_minute=540, duration_minute=90, status='draft',
            ),
            # Northbridge: DBS201 requires a lab -> B204 (40 seats == group size).
            SessionBooking(
                institution_id=northbridge.id, campus_id=main_campus.id, course_id=course_dbs201.id,
                lecturer_id=lecturer_sam.id, student_group_id=group_cs2.id, room_id=room_b204.id,
                day=0, start_minute=600, duration_minute=90, status='draft',
            ),
            SessionBooking(
                institution_id=northbridge.id, campus_id=main_campus.id, course_id=course_mth120.id,
                lecturer_id=lecturer_priya.id, student_group_id=group_cs1.id, room_id=room_c315.id,
                day=1, start_minute=540, duration_minute=90, status='draft',
            ),
            # Harbor: room H1 belongs to Harbor (baseline seeded a Northbridge room here).
            SessionBooking(
                institution_id=harbor.id, campus_id=harbor_campus.id, course_id=course_eng110.id,
                lecturer_id=lecturer_milo.id, student_group_id=group_eng.id, room_id=room_h1.id,
                day=0, start_minute=540, duration_minute=90, status='draft',
            ),
        ]
        session.add_all(bookings)
        session.commit()
