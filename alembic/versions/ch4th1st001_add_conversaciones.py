"""add agente_conversaciones table

Revision ID: ch4th1st001
Revises: ag1nt3c0de01
Create Date: 2026-06-02 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ch4th1st001"
down_revision: Union[str, None] = "ag1nt3c0de01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agente_conversaciones",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=50), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column(
            "mensajes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agente_conv_user_id", "agente_conversaciones", ["user_id"])
    op.create_index("ix_agente_conv_tenant_id", "agente_conversaciones", ["tenant_id"])
    op.create_index(
        "ix_agente_conv_user_updated",
        "agente_conversaciones",
        ["user_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_table("agente_conversaciones")
