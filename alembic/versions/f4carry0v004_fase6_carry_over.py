"""Fase 6 (REQ-07): carry-over de jornada en tareas de campo

Agrega a ``tareas``:
- ``carry_over_de``: id de la tarea original que esta continuación arrastra.
- ``intento_n``: número de jornada en que se intenta (1 = primera vez).

Revision ID: f4carry0v004
Revises: f3br1dg3003
Create Date: 2026-06-19 01:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4carry0v004"
down_revision: Union[str, None] = "f3br1dg3003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tareas", sa.Column("carry_over_de", sa.String(40), nullable=True))
    op.add_column(
        "tareas",
        sa.Column("intento_n", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_foreign_key(
        "fk_tareas_carry_over_de", "tareas", "tareas", ["carry_over_de"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_tareas_carry_over_de", "tareas", type_="foreignkey")
    op.drop_column("tareas", "intento_n")
    op.drop_column("tareas", "carry_over_de")
