"""Filtrado por permisos del RAG — el archivo más importante de seguridad.

Garantiza que el LLM solo reciba fragmentos de conocimiento a los que el usuario
autenticado tiene derecho. Se aplica en DOS barreras:

1. `build_chroma_where(ctx)`: filtro de metadatos que se envía a ChromaDB en la
   consulta (no se recupera lo prohibido).
2. `filtrar_candidatos(ctx, candidatos)`: segunda barrera en memoria sobre lo que
   devuelve el almacén (defensa en profundidad, por si el `where` fallara o el
   índice tuviera metadatos inesperados).

Reglas (todas deben cumplirse):
- nivel ∈ niveles visibles del rol (el nivel `reservado` solo está en la lista si
  `seguridad_reservada = True`).
- tenant ∈ {tenant del usuario, "global"}.
- área: documentos sin área (centinela "") son visibles a todos; los acotados a un
  área solo si el usuario tiene esa área. Los roles de alcance "global" (admin) no
  se restringen por área dentro de su tenant.
"""

from app.agente.context import UsuarioContexto

# Valor centinela para documentos que no están acotados a un área concreta.
SIN_AREA = ""


def build_chroma_where(ctx: UsuarioContexto) -> dict:
    """Construye el filtro de metadatos `where` para la consulta a ChromaDB."""
    condiciones: list[dict] = [
        {"nivel": {"$in": list(ctx.niveles_visibles)}},
        {"tenant_id": {"$in": [ctx.tenant_id, "global"]}},
    ]
    # Los directores (alcance no global) solo ven su(s) área(s) + documentos sin área.
    if ctx.alcance_datos != "global":
        condiciones.append({"area_id": {"$in": [SIN_AREA, *ctx.areas]}})
    return {"$and": condiciones}


def es_visible(ctx: UsuarioContexto, meta: dict) -> bool:
    """Decide si un fragmento es visible para el usuario (segunda barrera)."""
    if meta.get("nivel") not in ctx.niveles_visibles:
        return False
    if meta.get("tenant_id") not in (ctx.tenant_id, "global"):
        return False
    if ctx.alcance_datos != "global":
        area = meta.get("area_id") or SIN_AREA
        if area != SIN_AREA and area not in ctx.areas:
            return False
    return True


def filtrar_candidatos(ctx: UsuarioContexto, candidatos: list[dict]) -> list[dict]:
    """Filtra los candidatos recuperados; cada candidato debe traer `metadata`."""
    return [c for c in candidatos if es_visible(ctx, c.get("metadata", {}))]
