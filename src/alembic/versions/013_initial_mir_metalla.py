"""initial schema for Mir Metalla bot

Revision ID: 013
Revises:
Create Date: 2026-06-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("chat_id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=100), nullable=True),
        sa.Column("extra", sa.String(length=100), nullable=True),
        sa.Column("final_stage", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("answers_from_agent", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("chat_id"),
    )
    op.create_table(
        "messages",
        sa.Column("message_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.String(length=50), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=True),
        sa.Column("assistant_message", sa.Text(), nullable=True),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["users.chat_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("message_id"),
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("users")
