import os
import tempfile

# Point the app at an isolated SQLite file + local store BEFORE importing app.*
# (config.Settings and the engine are bound at import time).
_tmpdir = tempfile.mkdtemp(prefix="knowledge-test-").replace("\\", "/")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdir}/test.db"
os.environ["OBJECT_STORE_TYPE"] = "local"
os.environ["OBJECT_STORE_DIR"] = f"{_tmpdir}/objects"
os.environ["WORKER_ENABLED"] = "false"
os.environ["EMBEDDER"] = "hash"
os.environ["OCR_BACKEND"] = "none"
os.environ["RERANKER_BACKEND"] = "lexical"
os.environ["QDRANT_URL"] = ""

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def client(_clean_db):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def session(_clean_db):
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
