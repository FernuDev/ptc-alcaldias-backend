"""Marca / White-label (Fase 1): design tokens por tenant + historial

Agrega a ``tenants``:
- ``brand`` (JSONB): documento de design tokens con overrides del tenant.
- ``logo_path`` / ``favicon_path`` (String): claves de storage de activos subidos.
- ``brand_version`` (Integer): versión de marca, incrementa en cada guardado.

Crea ``tenant_brand_history``: snapshot inmutable por versión (para revertir).

Defaults reproducen el tema actual de MC: ``brand`` NULL ⇒ se resuelve con los
escalares existentes (``primario``/``secundario``/``dorado``) + defaults MC, por
lo que nada cambia visualmente hasta que un tenant configure su marca.

Revision ID: br4ndth3m01
Revises: r5org0nod01
Create Date: 2026-06-20 03:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "br4ndth3m01"
down_revision: Union[str, None] = "r5org0nod01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "brand", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column(
        "tenants", sa.Column("logo_path", sa.String(200), nullable=True)
    )
    op.add_column(
        "tenants", sa.Column("favicon_path", sa.String(200), nullable=True)
    )
    op.add_column(
        "tenants",
        sa.Column(
            "brand_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )

    op.create_table(
        "tenant_brand_history",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("updated_by", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_tenant_brand_history_tenant_id",
        "tenant_brand_history",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_tenant_brand_history_tenant_id"),
        "tenant_brand_history",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tenant_brand_history_tenant_id"),
        table_name="tenant_brand_history",
    )
    op.drop_constraint(
        "fk_tenant_brand_history_tenant_id",
        "tenant_brand_history",
        type_="foreignkey",
    )
    op.drop_table("tenant_brand_history")
    op.drop_column("tenants", "brand_version")
    op.drop_column("tenants", "favicon_path")
    op.drop_column("tenants", "logo_path")
    op.drop_column("tenants", "brand")
