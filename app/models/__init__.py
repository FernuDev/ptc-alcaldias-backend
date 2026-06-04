# Re-export all models so Alembic autogenerate can discover them
from app.models.base import Base
from app.models.tenant import Tenant
from app.models.user import User, user_areas
from app.models.categoria import Categoria, ObraCategoria
from app.models.colonia import Colonia
from app.models.cuadrilla import Cuadrilla, cuadrilla_especialidades
from app.models.contratista import Contratista
from app.models.reporte import Reporte, ReporteEvidencia, ReporteEvento
from app.models.obra import (
    Obra,
    ObraPresupuestoItem,
    ObraEquipo,
    ObraCalleAfectada,
    ObraTimeline,
    ObraDocumento,
    ObraEvidencia,
)
from app.models.notificacion import Notificacion
from app.models.audit_log import AuditLog
from app.models.refresh_token import RefreshToken
from app.models.agente_interaccion import AgenteInteraccion
from app.models.agente_accion import AgenteAccion
from app.models.agente_documento import AgenteDocumento
from app.models.agente_conversacion import AgenteConversacion

__all__ = [
    "Base",
    "Tenant",
    "User",
    "user_areas",
    "Categoria",
    "ObraCategoria",
    "Colonia",
    "Cuadrilla",
    "cuadrilla_especialidades",
    "Contratista",
    "Reporte",
    "ReporteEvidencia",
    "ReporteEvento",
    "Obra",
    "ObraPresupuestoItem",
    "ObraEquipo",
    "ObraCalleAfectada",
    "ObraTimeline",
    "ObraDocumento",
    "ObraEvidencia",
    "Notificacion",
    "AuditLog",
    "RefreshToken",
    "AgenteInteraccion",
    "AgenteAccion",
    "AgenteDocumento",
    "AgenteConversacion",
]
