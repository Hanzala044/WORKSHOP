import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.models import Base, Experiment
from app.services.experiments import finish_experiment, start_experiment


def test_persistent_sqlite_survives_new_connection(tmp_path):
    url = f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        experiment = start_experiment(db, "pricepilot", "Persisted")
        finish_experiment(db, experiment, {"count": 1})
        identifier = experiment.id
    engine.dispose()
    engine = create_engine(url)
    with Session(engine) as db:
        stored = db.scalar(select(Experiment).where(Experiment.id == identifier))
        assert stored.status == "completed"
        assert stored.output_metadata == {"count": 1}
        assert stored.duration_ms >= 0
    engine.dispose()


@pytest.mark.parametrize("kwargs", [
    {"allowed_hosts": ["*.example.com"]}, {"allowed_hosts": ["https://example.com"]},
    {"trusted_hosts": ["*"]}, {"cors_origins": ["*"]},
    {"cors_origins": ["http://localhost:5173/path"]},
    {"max_upload_bytes": 2048, "max_request_bytes": 1024},
])
def test_unsafe_config_rejected(kwargs):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **kwargs)


def test_secret_masked_and_hostname_normalized():
    settings = Settings(_env_file=None, groq_api_key="should-not-be-displayed", allowed_hosts=["SHOP.Example."])
    assert "should-not-be-displayed" not in repr(settings)
    assert settings.allowed_hosts == ["shop.example"]
