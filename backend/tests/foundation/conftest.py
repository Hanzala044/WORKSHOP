from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import get_settings
from app.database.models import Base
from app.database.session import get_db
from app.main import create_app


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(db, monkeypatch, tmp_path):
    config = get_settings().model_copy(update={"data_dir": tmp_path, "max_upload_bytes": 1024, "max_request_bytes": 4096})
    # Keep all lifespan work isolated, including the production database.
    import app.main as main
    import app.api.routes.health as health
    import app.api.routes.voicemind as voice
    import app.api.routes.settings as preferences
    monkeypatch.setattr(main, "get_settings", lambda: config)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(health, "get_settings", lambda: config)
    monkeypatch.setattr(voice, "get_settings", lambda: config)
    monkeypatch.setattr(preferences, "get_settings", lambda: config)
    application = create_app()
    application.dependency_overrides[get_db] = lambda: db
    with TestClient(application, base_url="http://localhost", raise_server_exceptions=False) as test_client:
        yield test_client
