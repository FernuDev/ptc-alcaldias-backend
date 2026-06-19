"""módulo de campo fase 2: integrantes, turnos, tareas, ubicaciones, mensajes

Revision ID: f3c5d7a9b201
Revises: e7b2a9c14d10
Create Date: 2026-06-18 16:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3c5d7a9b201"
down_revision: Union[str, None] = "e7b2a9c14d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Integrantes (nómina operativa real de cada cuadrilla) ──────────────────
    op.create_table(
        "integrantes",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("cuadrilla_id", sa.String(length=10), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.String(length=50), nullable=True),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("rol_campo", sa.String(length=15), nullable=False),
        sa.Column("telefono", sa.String(length=20), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["cuadrilla_id"], ["cuadrillas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_integrantes_cuadrilla_id"), "integrantes", ["cuadrilla_id"])
    op.create_index(op.f("ix_integrantes_tenant_id"), "integrantes", ["tenant_id"])

    # ── Turnos (jornada operativa abierta/cerrada) ─────────────────────────────
    op.create_table(
        "turnos",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("cuadrilla_id", sa.String(length=10), nullable=False),
        sa.Column(
            "inicio",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("fin", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estado", sa.String(length=10), nullable=False, server_default="abierto"),
        sa.ForeignKeyConstraint(["cuadrilla_id"], ["cuadrillas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_turnos_tenant_id"), "turnos", ["tenant_id"])
    op.create_index(op.f("ix_turnos_cuadrilla_id"), "turnos", ["cuadrilla_id"])

    # ── Tareas (trabajo despachado a cuadrilla/integrante) ─────────────────────
    op.create_table(
        "tareas",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("cuadrilla_id", sa.String(length=10), nullable=True),
        sa.Column("integrante_id", sa.String(length=40), nullable=True),
        sa.Column("origen_tipo", sa.String(length=10), nullable=False),
        sa.Column("reporte_id", sa.String(length=20), nullable=True),
        sa.Column("obra_id", sa.String(length=20), nullable=True),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("prioridad", sa.String(length=10), nullable=False, server_default="media"),
        sa.Column("estado", sa.String(length=12), nullable=False, server_default="pendiente"),
        sa.Column("orden_ruta", sa.Integer(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("colonia_id", sa.String(length=60), nullable=True),
        sa.Column("instrucciones", sa.Text(), nullable=True),
        sa.Column(
            "checklist",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
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
        sa.Column("fecha_cierre", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["cuadrilla_id"], ["cuadrillas.id"]),
        sa.ForeignKeyConstraint(["integrante_id"], ["integrantes.id"]),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.ForeignKeyConstraint(["reporte_id"], ["reportes.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tareas_tenant_id"), "tareas", ["tenant_id"])
    op.create_index(op.f("ix_tareas_cuadrilla_id"), "tareas", ["cuadrilla_id"])
    op.create_index("ix_tareas_tenant_estado", "tareas", ["tenant_id", "estado"])
    op.create_index("ix_tareas_cuadrilla_estado", "tareas", ["cuadrilla_id", "estado"])

    # ── Ubicaciones (serie temporal GPS para el mapa en vivo) ──────────────────
    op.create_table(
        "ubicaciones",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("cuadrilla_id", sa.String(length=10), nullable=False),
        sa.Column("integrante_id", sa.String(length=40), nullable=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["cuadrilla_id"], ["cuadrillas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["integrante_id"], ["integrantes.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ubicaciones_tenant_id"), "ubicaciones", ["tenant_id"])
    op.create_index(op.f("ix_ubicaciones_cuadrilla_id"), "ubicaciones", ["cuadrilla_id"])
    op.create_index("ix_ubicaciones_cuadrilla_ts", "ubicaciones", ["cuadrilla_id", "timestamp"])

    # ── Mensajes de campo (canal monitor ↔ campo) ──────────────────────────────
    op.create_table(
        "mensajes_campo",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("cuadrilla_id", sa.String(length=10), nullable=False),
        sa.Column("tarea_id", sa.String(length=40), nullable=True),
        sa.Column("autor_tipo", sa.String(length=10), nullable=False),
        sa.Column("autor_id", sa.String(length=50), nullable=True),
        sa.Column("tipo", sa.String(length=8), nullable=False),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("nota_voz_url", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["cuadrilla_id"], ["cuadrillas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tarea_id"], ["tareas.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_mensajes_campo_tenant_id"), "mensajes_campo", ["tenant_id"])
    op.create_index(op.f("ix_mensajes_campo_cuadrilla_id"), "mensajes_campo", ["cuadrilla_id"])
    op.create_index("ix_mensajes_campo_cuadrilla", "mensajes_campo", ["cuadrilla_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_mensajes_campo_cuadrilla", table_name="mensajes_campo")
    op.drop_index(op.f("ix_mensajes_campo_cuadrilla_id"), table_name="mensajes_campo")
    op.drop_index(op.f("ix_mensajes_campo_tenant_id"), table_name="mensajes_campo")
    op.drop_table("mensajes_campo")

    op.drop_index("ix_ubicaciones_cuadrilla_ts", table_name="ubicaciones")
    op.drop_index(op.f("ix_ubicaciones_cuadrilla_id"), table_name="ubicaciones")
    op.drop_index(op.f("ix_ubicaciones_tenant_id"), table_name="ubicaciones")
    op.drop_table("ubicaciones")

    op.drop_index("ix_tareas_cuadrilla_estado", table_name="tareas")
    op.drop_index("ix_tareas_tenant_estado", table_name="tareas")
    op.drop_index(op.f("ix_tareas_cuadrilla_id"), table_name="tareas")
    op.drop_index(op.f("ix_tareas_tenant_id"), table_name="tareas")
    op.drop_table("tareas")

    op.drop_index(op.f("ix_turnos_cuadrilla_id"), table_name="turnos")
    op.drop_index(op.f("ix_turnos_tenant_id"), table_name="turnos")
    op.drop_table("turnos")

    op.drop_index(op.f("ix_integrantes_tenant_id"), table_name="integrantes")
    op.drop_index(op.f("ix_integrantes_cuadrilla_id"), table_name="integrantes")
    op.drop_table("integrantes")
