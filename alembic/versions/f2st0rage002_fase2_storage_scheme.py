"""Fase 2 (REQ-04): esquema de almacenamiento documental por tenant

Agrega a ``tenants``:
- ``storage_scheme`` (nube_gestionada | conector_nas | subarrendamiento_dedicado).
- ``storage_config`` (JSONB del conector NAS, sin credenciales en claro).

Revision ID: f2st0rage002
Revises: f1ge0z0na001
Create Date: 2026-06-19 00:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2st0rage002"
down_revision: Union[str, None] = "f1ge0z0na001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "storage_scheme",
            sa.String(30),
            nullable=True,
            server_default="nube_gestionada",
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "storage_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "storage_config")
    op.drop_column("tenants", "storage_scheme")
