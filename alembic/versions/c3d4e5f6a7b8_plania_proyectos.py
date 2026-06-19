"""fase 6: Plan.IA proyectos y tareas

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-18 22:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "proyectos",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("tipo", sa.String(length=12), nullable=False, server_default="obra"),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column(
            "estado", sa.String(length=15), nullable=False, server_default="planeacion"
        ),
        sa.Column(
            "prioridad", sa.String(length=10), nullable=False, server_default="media"
        ),
        sa.Column("avance_pct", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("responsable_nombre", sa.String(length=120), nullable=True),
        sa.Column("area_id", sa.String(length=30), nullable=True),
        sa.Column("compromiso_id", sa.String(length=40), nullable=True),
        sa.Column("pdm_eje", sa.String(length=160), nullable=True),
        sa.Column("presupuesto_estimado", sa.DECIMAL(precision=14, scale=2), nullable=True),
        sa.Column("fecha_inicio", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fecha_fin_estimada", sa.DateTime(timezone=True), nullable=True),
        sa.Column("origen_zona", sa.String(length=160), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_proyectos_tenant_id"), "proyectos", ["tenant_id"])

    op.create_table(
        "proyecto_tareas",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("proyecto_id", sa.String(length=40), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column(
            "estado", sa.String(length=12), nullable=False, server_default="pendiente"
        ),
        sa.Column("avance_pct", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("fecha_inicio", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fecha_fin", sa.DateTime(timezone=True), nullable=True),
        sa.Column("depende_de", sa.String(length=40), nullable=True),
        sa.Column("responsable", sa.String(length=120), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["proyecto_id"], ["proyectos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_proyecto_tareas_proyecto_id"), "proyecto_tareas", ["proyecto_id"]
    )
    op.create_index(
        op.f("ix_proyecto_tareas_tenant_id"), "proyecto_tareas", ["tenant_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_proyecto_tareas_tenant_id"), table_name="proyecto_tareas")
    op.drop_index(op.f("ix_proyecto_tareas_proyecto_id"), table_name="proyecto_tareas")
    op.drop_table("proyecto_tareas")
    op.drop_index(op.f("ix_proyectos_tenant_id"), table_name="proyectos")
    op.drop_table("proyectos")
