# Build context: repository root (the backend imports the /pipeline package).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY pipeline /srv/pipeline
RUN pip install --no-cache-dir /srv/pipeline

COPY backend/requirements.txt /srv/backend/requirements.txt
RUN pip install --no-cache-dir -r /srv/backend/requirements.txt

COPY backend /srv/backend
WORKDIR /srv/backend

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && if [ \"$SEED_ON_START\" = \"true\" ]; then python -m app.seed $SEED_ARGS; fi && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
