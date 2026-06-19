"""spine fase 4: compromisos, tipo_afectacion en calles, versionado de archivos

Revision ID: a1b2c3d4e5f6
Revises: f3c5d7a9b201
Create Date: 2026-06-18 18:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f3c5d7a9b201"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Compromisos (metas públicas con avance medible) ────────────────────────
    op.create_table(
        "compromisos",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("area_id", sa.String(length=30), nullable=True),
        sa.Column("meta", sa.String(length=300), nullable=True),
        sa.Column("avance_pct", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column(
            "estado",
            sa.String(length=12),
            nullable=False,
            server_default="en_progreso",
        ),
        sa.Column("fecha_objetivo", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_compromisos_tenant_id"), "compromisos", ["tenant_id"])

    # ── tipo_afectacion en obra_calles_afectadas ───────────────────────────────
    op.add_column(
        "obra_calles_afectadas",
        sa.Column("tipo_afectacion", sa.String(length=10), nullable=True),
    )

    # ── Versionado de archivos ─────────────────────────────────────────────────
    op.add_column(
        "archivos",
        sa.Column("version", sa.SmallInteger(), nullable=False, server_default="1"),
    )
    op.add_column(
        "archivos",
        sa.Column("reemplaza_a", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "archivos",
        sa.Column(
            "es_actual",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("archivos", "es_actual")
    op.drop_column("archivos", "reemplaza_a")
    op.drop_column("archivos", "version")

    op.drop_column("obra_calles_afectadas", "tipo_afectacion")

    op.drop_index(op.f("ix_compromisos_tenant_id"), table_name="compromisos")
    op.drop_table("compromisos")
