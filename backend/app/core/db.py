from sqlmodel import Session, SQLModel, create_engine
from app.core.config import get_settings

settings = get_settings()
connect_args = {'check_same_thread': False} if settings.database_url.startswith('sqlite') else {}
engine = create_engine(settings.database_url, connect_args=connect_args, echo=False)


def get_session():
    with Session(engine) as session:
        yield session
