import importlib
import importlib.util

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.database.models import Base

settings = get_settings()
_url = settings.database_url or f"sqlite:///{(settings.data_dir / 'workshop.sqlite3').as_posix()}"
engine = create_engine(
    _url, connect_args={"check_same_thread": False, "timeout": 15} if _url.startswith("sqlite") else {},
    pool_pre_ping=True,
)
if _url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def sqlite_pragmas(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db


def init_db():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if importlib.util.find_spec("app.models.documents") is not None:
        importlib.import_module("app.models.documents")
    Base.metadata.create_all(bind=engine)
