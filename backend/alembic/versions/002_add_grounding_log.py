"""Add grounding_log table for M8.3 confidence logging.

Revision ID: 002
Revises: 001
Create Date: 2026-07-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "grounding_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("field_path", sa.Text(), nullable=False),
        sa.Column("extracted_value", postgresql.JSONB(), nullable=False),
        sa.Column("user_message_snippet", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=False),
        sa.Column("reverted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_grounding_log_session_id",
        "grounding_log",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_grounding_log_session_id", table_name="grounding_log")
    op.drop_table("grounding_log")
