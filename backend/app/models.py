"""SQLAlchemy ORM model for the sessions table."""

from sqlalchemy import Column, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from app.db import Base


class SessionRow(Base):
    __tablename__ = "sessions"

    session_id = Column(Text, primary_key=True)
    spec = Column(JSONB, nullable=False)
    history = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
