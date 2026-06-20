"""R5 Fase 1 (REQ-17): núcleo organizacional (árbol + capacidades + RBAC heredado)

Crea el organigrama configurable como dato:
- ``capacidades``: catálogo fijo de módulos asignables (proyectos, obras, …).
- ``org_nodos``: árbol jerárquico self-referencial por tenant (raíz = Alcalde).
- ``nodo_capacidades``: capacidades encendidas por nodo (con ``nivel_uso``).
- ``users.nodo_id`` + ``users.es_campo``: posición del usuario en el árbol y
  marca de personal de campo (solo app, sin backoffice).

Revision ID: r5org0nod01
Revises: f4carry0v004
Create Date: 2026-06-19 21:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r5org0nod01"
down_revision: Union[str, None] = "f4carry0v004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Catálogo de capacidades (fijo) ───────────────────────────────────────
    op.create_table(
        "capacidades",
        sa.Column("codigo", sa.String(30), primary_key=True),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default="0"),
    )

    # ── Árbol organizacional por tenant ──────────────────────────────────────
    op.create_table(
        "org_nodos",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("parent_id", sa.String(40), nullable=True),
        sa.Column("nivel", sa.String(20), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(160), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("cuadrilla_id", sa.String(10), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_foreign_key(
        "fk_org_nodos_tenant_id", "org_nodos", "tenants", ["tenant_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_org_nodos_parent_id",
        "org_nodos",
        "org_nodos",
        ["parent_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_org_nodos_cuadrilla_id",
        "org_nodos",
        "cuadrillas",
        ["cuadrilla_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_org_nodos_tenant_id"), "org_nodos", ["tenant_id"])
    op.create_index(op.f("ix_org_nodos_parent_id"), "org_nodos", ["parent_id"])

    # ── Capacidades encendidas por nodo ──────────────────────────────────────
    op.create_table(
        "nodo_capacidades",
        sa.Column("nodo_id", sa.String(40), primary_key=True),
        sa.Column("capacidad", sa.String(30), primary_key=True),
        sa.Column("nivel_uso", sa.String(10), nullable=False, server_default="usa"),
    )
    op.create_foreign_key(
        "fk_nodo_capacidades_nodo_id",
        "nodo_capacidades",
        "org_nodos",
        ["nodo_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_nodo_capacidades_capacidad",
        "nodo_capacidades",
        "capacidades",
        ["capacidad"],
        ["codigo"],
        ondelete="CASCADE",
    )

    # ── Usuario atado a un nodo + marca de campo ─────────────────────────────
    op.add_column("users", sa.Column("nodo_id", sa.String(40), nullable=True))
    op.add_column(
        "users",
        sa.Column("es_campo", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_foreign_key(
        "fk_users_nodo_id",
        "users",
        "org_nodos",
        ["nodo_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_users_nodo_id"), "users", ["nodo_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_users_nodo_id"), table_name="users")
    op.drop_constraint("fk_users_nodo_id", "users", type_="foreignkey")
    op.drop_column("users", "es_campo")
    op.drop_column("users", "nodo_id")

    op.drop_constraint(
        "fk_nodo_capacidades_capacidad", "nodo_capacidades", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_nodo_capacidades_nodo_id", "nodo_capacidades", type_="foreignkey"
    )
    op.drop_table("nodo_capacidades")

    op.drop_index(op.f("ix_org_nodos_parent_id"), table_name="org_nodos")
    op.drop_index(op.f("ix_org_nodos_tenant_id"), table_name="org_nodos")
    op.drop_constraint("fk_org_nodos_cuadrilla_id", "org_nodos", type_="foreignkey")
    op.drop_constraint("fk_org_nodos_parent_id", "org_nodos", type_="foreignkey")
    op.drop_constraint("fk_org_nodos_tenant_id", "org_nodos", type_="foreignkey")
    op.drop_table("org_nodos")

    op.drop_table("capacidades")
