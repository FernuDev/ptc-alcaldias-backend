"""spine fase 5: tramites y avisos

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-18 19:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Trámites (catálogo público de trámites y servicios) ────────────────────
    op.create_table(
        "tramites",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("dependencia", sa.String(length=160), nullable=False),
        sa.Column("area_id", sa.String(length=30), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column(
            "requisitos",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("costo", sa.String(length=120), nullable=True),
        sa.Column("tiempo_estimado", sa.String(length=120), nullable=True),
        sa.Column("vigencia", sa.String(length=120), nullable=True),
        sa.Column(
            "documentos",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("donde_acudir", sa.String(length=300), nullable=True),
        sa.Column("horarios", sa.String(length=160), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tramites_tenant_id"), "tramites", ["tenant_id"])

    # ── Avisos y campañas institucionales ──────────────────────────────────────
    op.create_table(
        "avisos",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("cuerpo", sa.Text(), nullable=False),
        sa.Column(
            "tipo",
            sa.String(length=12),
            nullable=False,
            server_default="aviso",
        ),
        sa.Column("area_id", sa.String(length=30), nullable=True),
        sa.Column("segmento", sa.String(length=120), nullable=True),
        sa.Column(
            "fecha",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "activo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_avisos_tenant_id"), "avisos", ["tenant_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_avisos_tenant_id"), table_name="avisos")
    op.drop_table("avisos")

    op.drop_index(op.f("ix_tramites_tenant_id"), table_name="tramites")
    op.drop_table("tramites")
