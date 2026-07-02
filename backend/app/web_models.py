"""SQLAlchemy model for the web rebuild, shaped like ai-system's Note model:
an owner field, JSON blob column(s), timestamps via a TimestampMixin.

Separate from app/models.py (SessionRow/GroundingLogRow) — that module and
its Postgres-backed table stay exactly as they are.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Text
from sqlalchemy.orm import declared_attr

from app.web_db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    @declared_attr
    def created_at(cls):
        return Column(DateTime, default=_utcnow, nullable=False)

    @declared_attr
    def updated_at(cls):
        return Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)


class IntakeSession(TimestampMixin, Base):
    """One user's intake state: session_id, owner, and the spec/history JSON blobs."""

    __tablename__ = "intake_sessions"

    session_id = Column(Text, primary_key=True)
    owner = Column(Text, nullable=True, index=True)
    spec_json = Column(JSON, nullable=False)
    history_json = Column(JSON, nullable=False)
