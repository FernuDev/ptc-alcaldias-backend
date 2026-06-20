# Re-export all models so Alembic autogenerate can discover them
from app.models.agente_accion import AgenteAccion
from app.models.agente_conversacion import AgenteConversacion
from app.models.agente_documento import AgenteDocumento
from app.models.agente_interaccion import AgenteInteraccion
from app.models.archivo import Archivo
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.brand_history import TenantBrandHistory
from app.models.campo import Mensaje, Tarea, Turno, Ubicacion
from app.models.categoria import Categoria, ObraCategoria
from app.models.colonia import Colonia
from app.models.compromiso import Compromiso
from app.models.contratista import Contratista
from app.models.cuadrilla import Cuadrilla, Integrante, cuadrilla_especialidades
from app.models.notificacion import Notificacion
from app.models.obra import (
    Obra,
    ObraCalleAfectada,
    ObraDocumento,
    ObraEquipo,
    ObraEvidencia,
    ObraPresupuestoItem,
    ObraTimeline,
)
from app.models.org_nodo import Capacidad, OrgNodo, nodo_capacidades
from app.models.proyecto import (
    Proyecto,
    ProyectoAprobacion,
    ProyectoRiesgo,
    ProyectoStakeholder,
    ProyectoTarea,
)
from app.models.refresh_token import RefreshToken
from app.models.reporte import Reporte, ReporteEvento, ReporteEvidencia
from app.models.solicitud_arco import SolicitudARCO
from app.models.tenant import Tenant
from app.models.tramite import Aviso, Tramite
from app.models.user import User, user_areas

__all__ = [
    "Base",
    "Tenant",
    "TenantBrandHistory",
    "User",
    "user_areas",
    "Categoria",
    "ObraCategoria",
    "Colonia",
    "Cuadrilla",
    "Integrante",
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
    "OrgNodo",
    "Capacidad",
    "nodo_capacidades",
    "AuditLog",
    "RefreshToken",
    "AgenteInteraccion",
    "AgenteAccion",
    "AgenteDocumento",
    "AgenteConversacion",
    "SolicitudARCO",
    "Archivo",
    "Turno",
    "Tarea",
    "Ubicacion",
    "Mensaje",
    "Compromiso",
    "Tramite",
    "Aviso",
    "Proyecto",
    "ProyectoTarea",
    "ProyectoStakeholder",
    "ProyectoRiesgo",
    "ProyectoAprobacion",
]
