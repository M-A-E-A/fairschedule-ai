"""FairSchedule AI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, ai, auth, bookings, csv_imports, dashboard, rooms, scheduling
from app.core.config import get_settings
from app.core.db import engine
from app.core.migrations import run_migrations
from app.seed import seed_demo_data


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    run_migrations()
    seed_demo_data(engine)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title='FairSchedule AI', version='1.0.0', lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.backend_cors_origins.split(',') if origin.strip()],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    for router in (
        auth.router,
        auth.legacy_router,
        dashboard.router,
        rooms.router,
        bookings.router,
        scheduling.router,
        csv_imports.router,
        admin.router,
        ai.router,
    ):
        app.include_router(router)

    @app.get('/health')
    def health() -> dict[str, str]:
        return {'status': 'ok'}

    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn

    uvicorn.run('app.main:app', host='0.0.0.0', port=8000, reload=True)
