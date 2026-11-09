from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, SQLModel, delete, select

from app.core.config import get_settings
from app.core.db import engine, get_session
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.models.tenant import AuditEvent, Building, Campus, Course, Department, Institution, Lecturer, Room, ScheduleProposal, SessionBooking, StudentGroup, User
from app.schemas.auth import AuthToken, LoginRequest
from app.services.scheduler import generate_schedule_rows

app = FastAPI(title='FairSchedule AI', version='0.1.0')
settings = get_settings()
security = HTTPBearer(auto_error=False)


def require_auth(credentials: HTTPAuthorizationCredentials = Security(security), session: Session = Depends(get_session)) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='missing token')
    try:
        payload = decode_access_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid token') from exc
    user = session.exec(select(User).where(User.email == payload.get('sub'))).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='user not found')
    return user


@app.on_event('startup')
def startup():
    SQLModel.metadata.create_all(engine)
    seed_demo_data()


app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.backend_cors_origins.split(',') if origin.strip()],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


def seed_demo_data() -> None:
    with Session(engine) as session:
        if session.exec(select(User)).first() is not None:
            return

        for model in [AuditEvent, ScheduleProposal, SessionBooking, User, StudentGroup, Lecturer, Course, Room, Campus, Institution, Department, Building]:
            session.exec(delete(model))
        session.commit()

        northbridge = Institution(name='Northbridge University', slug='northbridge', tenant_code='NBU')
        harbor = Institution(name='Harbor College', slug='harbor', tenant_code='HRC')
        session.add_all([northbridge, harbor])
        session.commit()
        session.refresh(northbridge)
        session.refresh(harbor)

        north_campus = Campus(name='Main Campus', slug='main', institution_id=northbridge.id)
        north_campus2 = Campus(name='Tech Park', slug='tech-park', institution_id=northbridge.id)
        harbor_campus = Campus(name='Harbor South', slug='harbor-south', institution_id=harbor.id)
        session.add_all([north_campus, north_campus2, harbor_campus])
        session.commit()

        rooms = [
            Room(institution_id=northbridge.id, campus_id=north_campus.id, name='A101', capacity=80, room_type='lecture', equipment='projector'),
            Room(institution_id=northbridge.id, campus_id=north_campus.id, name='B204', capacity=40, room_type='lab', equipment='computers'),
            Room(institution_id=northbridge.id, campus_id=north_campus.id, name='C315', capacity=120, room_type='lecture', equipment='projector,screen'),
            Room(institution_id=northbridge.id, campus_id=north_campus2.id, name='T12', capacity=65, room_type='seminar', equipment='whiteboard'),
            Room(institution_id=harbor.id, campus_id=harbor_campus.id, name='H1', capacity=70, room_type='lecture', equipment='projector'),
        ]
        session.add_all(rooms)
        session.commit()

        courses = [
            Course(institution_id=northbridge.id, code='CS101', name='Intro to Computing'),
            Course(institution_id=northbridge.id, code='DBS201', name='Database Systems'),
            Course(institution_id=northbridge.id, code='MTH120', name='Discrete Mathematics'),
            Course(institution_id=harbor.id, code='ENG110', name='Engineering Foundations'),
        ]
        session.add_all(courses)
        session.commit()

        lecturers = [
            Lecturer(institution_id=northbridge.id, name='Ada Reed', email='ada@northbridge.edu'),
            Lecturer(institution_id=northbridge.id, name='Sam Chen', email='sam@northbridge.edu'),
            Lecturer(institution_id=northbridge.id, name='Priya Nair', email='priya@northbridge.edu'),
            Lecturer(institution_id=harbor.id, name='Milo Stone', email='milo@harbor.edu'),
        ]
        session.add_all(lecturers)
        session.commit()

        student_groups = [
            StudentGroup(institution_id=northbridge.id, name='CS Year 1'),
            StudentGroup(institution_id=northbridge.id, name='CS Year 2'),
            StudentGroup(institution_id=harbor.id, name='Engineering Cohort'),
        ]
        session.add_all(student_groups)
        session.commit()

        users = [
            User(email='admin@northbridge.edu', password_hash=hash_password('demo-admin'), full_name='Alice Admin', role='administrator', institution_id=northbridge.id),
            User(email='operator@northbridge.edu', password_hash=hash_password('demo-operator'), full_name='Omar Operator', role='campus_operator', institution_id=northbridge.id),
            User(email='faculty@northbridge.edu', password_hash=hash_password('demo-faculty'), full_name='Fiona Faculty', role='faculty', institution_id=northbridge.id),
            User(email='student@northbridge.edu', password_hash=hash_password('demo-student'), full_name='Sara Student', role='student', institution_id=northbridge.id),
            User(email='admin@harbor.edu', password_hash=hash_password('demo-admin-harbor'), full_name='Hannah Harbor', role='administrator', institution_id=harbor.id),
        ]
        session.add_all(users)
        session.commit()

        bookings = [
            SessionBooking(institution_id=northbridge.id, campus_id=north_campus.id, course_id=courses[0].id, lecturer_id=lecturers[0].id, student_group_id=student_groups[0].id, room_id=rooms[0].id, day=0, start_minute=540, duration_minute=90, status='draft'),
            SessionBooking(institution_id=northbridge.id, campus_id=north_campus.id, course_id=courses[1].id, lecturer_id=lecturers[1].id, student_group_id=student_groups[1].id, room_id=rooms[2].id, day=0, start_minute=600, duration_minute=90, status='draft'),
            SessionBooking(institution_id=northbridge.id, campus_id=north_campus.id, course_id=courses[2].id, lecturer_id=lecturers[2].id, student_group_id=student_groups[0].id, room_id=rooms[1].id, day=1, start_minute=540, duration_minute=90, status='draft'),
            SessionBooking(institution_id=harbor.id, campus_id=harbor_campus.id, course_id=courses[3].id, lecturer_id=lecturers[3].id, student_group_id=student_groups[2].id, room_id=rooms[3].id, day=0, start_minute=540, duration_minute=90, status='draft'),
        ]
        session.add_all(bookings)
        session.commit()


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@app.post('/auth/login', response_model=AuthToken)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> AuthToken:
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid credentials')
    token = create_access_token(user.email, user.role, user.institution_id)
    return AuthToken(access_token=token, role=user.role, institution_id=user.institution_id)


@app.get('/auth/me')
def auth_me(current_user: User = Depends(require_auth)) -> dict[str, Any]:
    return {'email': current_user.email, 'role': current_user.role, 'institution_id': current_user.institution_id}


@app.get('/demo/tenant-summary')
def demo_tenant_summary(session: Session = Depends(get_session)) -> dict[str, Any]:
    institutions = session.exec(select(Institution)).all()
    result = []
    for inst in institutions:
        campus_count = session.exec(select(Campus).where(Campus.institution_id == inst.id)).all().__len__()
        result.append({
            'id': inst.id,
            'name': inst.name,
            'slug': inst.slug,
            'campus_count': campus_count,
        })
    return {'institutions': result}


@app.get('/institutions/{institution_id}/rooms')
def list_rooms_for_institution(institution_id: int, current_user: User = Depends(require_auth), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    if current_user.institution_id != institution_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='tenant mismatch')
    rows = session.exec(select(Room).where(Room.institution_id == institution_id)).all()
    return [{'id': room.id, 'name': room.name, 'capacity': room.capacity, 'room_type': room.room_type, 'campus_id': room.campus_id} for room in rows]


@app.get('/dashboard/overview')
def dashboard_overview(current_user: User = Depends(require_auth), session: Session = Depends(get_session)) -> dict[str, Any]:
    institutions = session.exec(select(Institution).where(Institution.id == current_user.institution_id)).all()
    campuses = session.exec(select(Campus).where(Campus.institution_id == current_user.institution_id)).all()
    rooms = session.exec(select(Room).where(Room.institution_id == current_user.institution_id)).all()
    courses = session.exec(select(Course).where(Course.institution_id == current_user.institution_id)).all()
    lecturers = session.exec(select(Lecturer).where(Lecturer.institution_id == current_user.institution_id)).all()
    student_groups = session.exec(select(StudentGroup).where(StudentGroup.institution_id == current_user.institution_id)).all()
    sessions = session.exec(select(SessionBooking).where(SessionBooking.institution_id == current_user.institution_id)).all()
    return {
        'institution_id': current_user.institution_id,
        'institution_name': institutions[0].name if institutions else 'Unknown',
        'campuses': len(campuses),
        'rooms': len(rooms),
        'courses': len(courses),
        'lecturers': len(lecturers),
        'student_groups': len(student_groups),
        'sessions': len(sessions),
    }


@app.post('/schedules/generate')
def generate_schedule(payload: dict[str, Any], current_user: User = Depends(require_auth), session: Session = Depends(get_session)) -> dict[str, Any]:
    institution_id = payload.get('institution_id')
    campus_id = payload.get('campus_id', 1)
    if current_user.institution_id != institution_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='tenant mismatch')
    rows = session.exec(select(SessionBooking).where(SessionBooking.institution_id == institution_id, SessionBooking.campus_id == campus_id)).all()
    rooms = session.exec(select(Room).where(Room.institution_id == institution_id, Room.campus_id == campus_id)).all()
    schedule_rows = []
    for booking in rows:
        course = session.exec(select(Course).where(Course.id == booking.course_id)).first()
        schedule_rows.append({
            'id': booking.id,
            'course_name': course.name if course else 'Course',
            'day': booking.day,
            'start_minute': booking.start_minute,
            'duration_minute': booking.duration_minute,
        })
    room_rows = [{'id': room.id, 'name': room.name, 'capacity': room.capacity} for room in rooms]
    result = generate_schedule_rows(institution_id, campus_id, schedule_rows, room_rows)
    audit = AuditEvent(institution_id=institution_id, user_email=current_user.email, event_type='schedule_generated', message='Generated a draft schedule')
    session.add(audit)
    session.commit()
    return {'status': result['status'], 'schedule': result['rows']}


@app.post('/ai/chat')
def ai_chat(payload: dict[str, str], current_user: User = Depends(require_auth)) -> dict[str, str]:
    prompt = payload.get('prompt', '')
    if not prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='prompt required')
    return {'answer': f'AI is not configured for this demo. Request: {prompt}. The backend can only provide safe, authorized data-backed responses when AI_PROVIDER is set.'}


@app.get('/sso/config')
def sso_config() -> dict[str, str]:
    return {'provider': 'none', 'status': 'demo only', 'notes': 'Configure Google OAuth or an OIDC provider via environment variables.'}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app.main:app', host='0.0.0.0', port=8000, reload=True)
