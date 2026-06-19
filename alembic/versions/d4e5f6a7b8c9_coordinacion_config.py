"""fase 6+: capa de coordinación Plan.IA y configuración persistente por tenant

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-18 22:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Configuración persistente del tenant (módulo 13) ────────────────────
    op.add_column("tenants", sa.Column("titular_nombre", sa.String(160), nullable=True))
    op.add_column("tenants", sa.Column("titular_cargo", sa.String(160), nullable=True))
    op.add_column("tenants", sa.Column("contacto", sa.String(200), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("sla_dias", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("flujos", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("checklists", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # ── Coordinación de proyectos ───────────────────────────────────────────
    op.create_table(
        "proyecto_stakeholders",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("proyecto_id", sa.String(40), nullable=False),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("nombre", sa.String(160), nullable=False),
        sa.Column("organizacion", sa.String(160), nullable=True),
        sa.Column("rol", sa.String(15), nullable=False, server_default="interesado"),
        sa.Column("postura", sa.String(10), nullable=False, server_default="neutral"),
        sa.Column("contacto", sa.String(160), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["proyecto_id"], ["proyectos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_proyecto_stakeholders_proyecto_id"),
        "proyecto_stakeholders",
        ["proyecto_id"],
    )
    op.create_index(
        op.f("ix_proyecto_stakeholders_tenant_id"),
        "proyecto_stakeholders",
        ["tenant_id"],
    )

    op.create_table(
        "proyecto_riesgos",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("proyecto_id", sa.String(40), nullable=False),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("probabilidad", sa.String(6), nullable=False, server_default="media"),
        sa.Column("impacto", sa.String(6), nullable=False, server_default="medio"),
        sa.Column("mitigacion", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(14), nullable=False, server_default="abierto"),
        sa.ForeignKeyConstraint(["proyecto_id"], ["proyectos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_proyecto_riesgos_proyecto_id"), "proyecto_riesgos", ["proyecto_id"]
    )
    op.create_index(
        op.f("ix_proyecto_riesgos_tenant_id"), "proyecto_riesgos", ["tenant_id"]
    )

    op.create_table(
        "proyecto_aprobaciones",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("proyecto_id", sa.String(40), nullable=False),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("etapa", sa.String(120), nullable=False),
        sa.Column("responsable", sa.String(120), nullable=True),
        sa.Column("estado", sa.String(10), nullable=False, server_default="pendiente"),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fecha_resolucion", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["proyecto_id"], ["proyectos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_proyecto_aprobaciones_proyecto_id"),
        "proyecto_aprobaciones",
        ["proyecto_id"],
    )
    op.create_index(
        op.f("ix_proyecto_aprobaciones_tenant_id"),
        "proyecto_aprobaciones",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_table("proyecto_aprobaciones")
    op.drop_table("proyecto_riesgos")
    op.drop_table("proyecto_stakeholders")
    op.drop_column("tenants", "checklists")
    op.drop_column("tenants", "flujos")
    op.drop_column("tenants", "sla_dias")
    op.drop_column("tenants", "contacto")
    op.drop_column("tenants", "titular_cargo")
    op.drop_column("tenants", "titular_nombre")
