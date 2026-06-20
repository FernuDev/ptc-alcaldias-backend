"""Fase 1 (REQ-09): PostGIS para el expediente de zona

- Habilita PostGIS.
- Agrega a ``reportes`` una columna generada ``geom`` (Point, 4326) derivada de
  lng/lat + índice GiST (insumo de ST_ClusterDBSCAN).
- Crea la tabla puente ``proyecto_reporte_relaciones`` (reportes del cluster
  vinculados al proyecto generado).
- Agrega ``tenants.zona_params`` (umbral/ventana_dias/radio_m del clustering).

Revision ID: f1ge0z0na001
Revises: d4e5f6a7b8c9
Create Date: 2026-06-19 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f1ge0z0na001"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── PostGIS + geometría generada de reportes (OPCIONAL) ─────────────────
    # PostGIS sólo se habilita si la extensión está disponible en el servidor.
    # En un Postgres plano (p. ej. la instancia de producción) se omite la
    # geometría y el expediente de zona degrada a clustering no-espacial; el
    # servicio detecta en runtime si existe la columna ``geom``.
    conn = op.get_bind()
    postgis_disponible = bool(
        conn.execute(
            sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'postgis'")
        ).scalar()
    )
    if postgis_disponible:
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        op.execute(
            "ALTER TABLE reportes ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326) "
            "GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lng, lat), 4326)) STORED"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_reportes_geom ON reportes USING GIST (geom)"
        )
    else:
        print(
            "[f1ge0z0na001] PostGIS no disponible en este servidor; se omite la "
            "columna geom. El expediente de zona usará clustering no-espacial."
        )

    # ── Puente proyecto ↔ reportes (cluster del expediente de zona) ──────────
    op.create_table(
        "proyecto_reporte_relaciones",
        sa.Column("proyecto_id", sa.String(40), nullable=False),
        sa.Column("reporte_id", sa.String(20), nullable=False),
        sa.ForeignKeyConstraint(["proyecto_id"], ["proyectos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reporte_id"], ["reportes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("proyecto_id", "reporte_id"),
    )
    op.create_index(
        op.f("ix_proyecto_reporte_relaciones_reporte_id"),
        "proyecto_reporte_relaciones",
        ["reporte_id"],
    )

    # ── Parámetros de clustering por tenant ─────────────────────────────────
    op.add_column(
        "tenants",
        sa.Column("zona_params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "zona_params")
    op.drop_index(
        op.f("ix_proyecto_reporte_relaciones_reporte_id"),
        table_name="proyecto_reporte_relaciones",
    )
    op.drop_table("proyecto_reporte_relaciones")
    op.execute("DROP INDEX IF EXISTS ix_reportes_geom")
    op.execute("ALTER TABLE reportes DROP COLUMN IF EXISTS geom")
    # No se elimina la extensión PostGIS (puede usarse en otros lugares).
