"""solicitudes_arco, archivos y evidencia geoetiquetada

Revision ID: e7b2a9c14d10
Revises: d4e1f00d5ec1
Create Date: 2026-06-18 14:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7b2a9c14d10"
down_revision: Union[str, None] = "d4e1f00d5ec1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Solicitudes ARCO (privacidad / derechos de datos personales) ──────────
    op.create_table(
        "solicitudes_arco",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("tipo", sa.String(length=15), nullable=False),
        sa.Column("email_solicitante", sa.String(length=120), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column(
            "estado", sa.String(length=20), nullable=False, server_default="recibida"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_solicitudes_arco_tenant_id"), "solicitudes_arco", ["tenant_id"]
    )

    # ── Registro central de archivos subidos ──────────────────────────────────
    op.create_table(
        "archivos",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("categoria", sa.String(length=30), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=True),
        sa.Column("entity_id", sa.String(length=40), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_archivos_tenant_id"), "archivos", ["tenant_id"])
    op.create_index(
        "ix_archivos_tenant_categoria", "archivos", ["tenant_id", "categoria"]
    )
    op.create_index("ix_archivos_entity", "archivos", ["entity_type", "entity_id"])

    # ── Evidencia geoetiquetada en reporte_evidencias (columnas nullable) ─────
    op.add_column(
        "reporte_evidencias", sa.Column("lat", sa.Float(), nullable=True)
    )
    op.add_column(
        "reporte_evidencias", sa.Column("lng", sa.Float(), nullable=True)
    )
    op.add_column(
        "reporte_evidencias",
        sa.Column("timestamp_captura", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reporte_evidencias", sa.Column("momento", sa.String(length=10), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("reporte_evidencias", "momento")
    op.drop_column("reporte_evidencias", "timestamp_captura")
    op.drop_column("reporte_evidencias", "lng")
    op.drop_column("reporte_evidencias", "lat")

    op.drop_index("ix_archivos_entity", table_name="archivos")
    op.drop_index("ix_archivos_tenant_categoria", table_name="archivos")
    op.drop_index(op.f("ix_archivos_tenant_id"), table_name="archivos")
    op.drop_table("archivos")

    op.drop_index(op.f("ix_solicitudes_arco_tenant_id"), table_name="solicitudes_arco")
    op.drop_table("solicitudes_arco")
