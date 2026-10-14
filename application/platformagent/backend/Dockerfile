FROM python:3.11-slim

ENV POETRY_VERSION=2.1.3 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/platformagent/backend/src

WORKDIR /app/platformagent/backend

RUN pip install "poetry==$POETRY_VERSION"

COPY ouroboros/ /app/ouroboros/
COPY platformagent/backend/pyproject.toml platformagent/backend/poetry.lock ./
RUN poetry install --only main --no-root --no-ansi

COPY platformagent/backend/ ./

EXPOSE 8000

CMD ["uvicorn", "smartagent.main:app", "--host", "0.0.0.0", "--port", "8000"]
