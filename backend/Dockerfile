FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# Startup runs migrations unconditionally (app.main lifespan ->
# app.core.migrations), reading /app/alembic.ini and /app/alembic. Without
# these copies the image only boots when Compose bind-mounts ./backend:/app
# over it (R-015); a standalone `docker run` crashes at startup.
COPY alembic.ini ./
COPY alembic ./alembic
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
