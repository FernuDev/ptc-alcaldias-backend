"""add agente institucional tables

Revision ID: ag1nt3c0de01
Revises: bf282849403f
Create Date: 2026-06-01 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ag1nt3c0de01"
down_revision: Union[str, None] = "bf282849403f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Flag de acceso a conocimiento reservado en users.
    op.add_column(
        "users",
        sa.Column(
            "puede_ver_reservado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Bitácora de interacciones.
    op.create_table(
        "agente_interacciones",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=50), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("rol", sa.String(length=20), nullable=False),
        sa.Column("canal", sa.String(length=20), nullable=False, server_default="chat"),
        sa.Column("pregunta", sa.Text(), nullable=False),
        sa.Column("respuesta", sa.Text(), nullable=False),
        sa.Column("fuentes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sin_informacion", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agente_int_user_ts", "agente_interacciones", ["user_id", "created_at"])
    op.create_index(
        op.f("ix_agente_interacciones_tenant_id"), "agente_interacciones", ["tenant_id"]
    )
    op.create_index(op.f("ix_agente_interacciones_user_id"), "agente_interacciones", ["user_id"])

    # Acciones preparadas (human-in-the-loop).
    op.create_table(
        "agente_acciones",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=50), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.String(length=50), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="pendiente"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agente_acc_user_estado", "agente_acciones", ["user_id", "estado"])
    op.create_index(op.f("ix_agente_acciones_tenant_id"), "agente_acciones", ["tenant_id"])
    op.create_index(op.f("ix_agente_acciones_user_id"), "agente_acciones", ["user_id"])

    # Metadatos de documentos ingestados (espejo de ChromaDB).
    op.create_table(
        "agente_documentos",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False, server_default="global"),
        sa.Column("titulo", sa.String(length=300), nullable=False),
        sa.Column("nivel_visibilidad", sa.String(length=20), nullable=False),
        sa.Column("area_id", sa.String(length=30), nullable=True),
        sa.Column("fuente", sa.String(length=300), nullable=True),
        sa.Column("fragmentos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agente_doc_tenant_nivel", "agente_documentos", ["tenant_id", "nivel_visibilidad"]
    )


def downgrade() -> None:
    op.drop_index("ix_agente_doc_tenant_nivel", table_name="agente_documentos")
    op.drop_table("agente_documentos")
    op.drop_index(op.f("ix_agente_acciones_user_id"), table_name="agente_acciones")
    op.drop_index(op.f("ix_agente_acciones_tenant_id"), table_name="agente_acciones")
    op.drop_index("ix_agente_acc_user_estado", table_name="agente_acciones")
    op.drop_table("agente_acciones")
    op.drop_index(op.f("ix_agente_interacciones_user_id"), table_name="agente_interacciones")
    op.drop_index(op.f("ix_agente_interacciones_tenant_id"), table_name="agente_interacciones")
    op.drop_index("ix_agente_int_user_ts", table_name="agente_interacciones")
    op.drop_table("agente_interacciones")
    op.drop_column("users", "puede_ver_reservado")
