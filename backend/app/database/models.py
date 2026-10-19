from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    module: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    output_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
