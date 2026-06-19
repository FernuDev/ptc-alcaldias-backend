"""Agente Ejecutivo — asistente estratégico del Alcalde (cross-direcciones).

Reutiliza la infraestructura del Agente Institucional (motor LLM DeepSeek) sin
editarla. Expone su lógica a través de ``orchestrator``.
"""

from app.agente_ejecutivo import orchestrator, system_prompt

__all__ = ["orchestrator", "system_prompt"]
