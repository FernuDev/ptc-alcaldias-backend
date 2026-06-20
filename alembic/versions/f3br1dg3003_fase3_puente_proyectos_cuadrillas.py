"""Fase 3 (REQ-07/QA-A): puente Proyectos ↔ Cuadrillas (ticket espejo)

Agrega a ``tareas`` (tareas de campo):
- ``proyecto_id`` / ``proyecto_tarea_id``: vínculo al proyecto/tarea de origen.
- ``cierre_nota``: nota/evidencia de cierre que se replica a la tarea de proyecto.

Revision ID: f3br1dg3003
Revises: f2st0rage002
Create Date: 2026-06-19 01:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3br1dg3003"
down_revision: Union[str, None] = "f2st0rage002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tareas", sa.Column("proyecto_id", sa.String(40), nullable=True))
    op.add_column(
        "tareas", sa.Column("proyecto_tarea_id", sa.String(40), nullable=True)
    )
    op.add_column("tareas", sa.Column("cierre_nota", sa.Text(), nullable=True))
    op.create_index(
        op.f("ix_tareas_proyecto_tarea_id"), "tareas", ["proyecto_tarea_id"]
    )
    op.create_foreign_key(
        "fk_tareas_proyecto_id", "tareas", "proyectos", ["proyecto_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_tareas_proyecto_tarea_id",
        "tareas",
        "proyecto_tareas",
        ["proyecto_tarea_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_tareas_proyecto_tarea_id", "tareas", type_="foreignkey")
    op.drop_constraint("fk_tareas_proyecto_id", "tareas", type_="foreignkey")
    op.drop_index(op.f("ix_tareas_proyecto_tarea_id"), table_name="tareas")
    op.drop_column("tareas", "cierre_nota")
    op.drop_column("tareas", "proyecto_tarea_id")
    op.drop_column("tareas", "proyecto_id")
