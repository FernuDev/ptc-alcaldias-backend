"""unique index on refresh_tokens.token_hash

Revision ID: d4e1f00d5ec1
Revises: ch4th1st001
Create Date: 2026-06-18 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d4e1f00d5ec1"
down_revision: Union[str, None] = "ch4th1st001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Endurecimiento: el hash de cada refresh token debe ser único.
    # Evita colisiones/reuso y refuerza la rotación de tokens.
    op.create_index(
        "uq_refresh_tokens_token_hash",
        "refresh_tokens",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_refresh_tokens_token_hash", table_name="refresh_tokens")
