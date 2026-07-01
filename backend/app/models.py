"""SQLAlchemy ORM models for the chatbot persistence layer."""

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, Text, func
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


class GroundingLogRow(Base):
    """One row per field that was newly extracted in a turn.

    Persists the grounding check result (M8.1) so confidence scores can be
    reviewed across restarts and used to tune the grounding threshold over time.

    confidence is the keyword-overlap fraction (0.0–1.0): the share of
    significant tokens from the extracted value that appear in the user message.
    grounded = confidence > 0.0; reverted = the field was rolled back because
    confidence was 0.0.
    """
    __tablename__ = "grounding_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Text, nullable=False, index=True)
    turn_number = Column(Integer, nullable=False)
    field_path = Column(Text, nullable=False)
    extracted_value = Column(JSONB, nullable=False)
    user_message_snippet = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    grounded = Column(Boolean, nullable=False)
    reverted = Column(Boolean, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
