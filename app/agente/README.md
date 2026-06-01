# Agente Institucional

Copiloto conversacional de IA embebido en el backend de la Plataforma Ciudadana.
Ayuda a funcionarios a consultar conocimiento (RAG citado), clasificar reportes,
obtener métricas en lenguaje natural y **preparar** acciones que un humano
confirma. Está montado como módulo del backend (`app/agente/`) y reutiliza su
auth/JWT, Postgres, modelos y auditoría.

## Principios de diseño
- **Permisos antes del modelo.** El `UsuarioContexto` se deriva del JWT real
  (`app/agente/context.py`), nunca del body. El RAG filtra por tenant + área +
  nivel de visibilidad **antes** de construir el prompt (`rag/permissions.py`),
  en dos barreras: filtro `where` en ChromaDB y re-filtro en memoria.
- **Human-in-the-loop.** El agente PREPARA acciones (`actions.py`); solo se
  ejecutan tras `POST /actions/confirm`, reutilizando los services existentes y
  registrando en `audit_logs`.
- **Fundamentación y "no sé".** Responde solo con lo recuperado; si no hay
  contexto, lo dice. Toda interacción queda en `agente_interacciones` (bitácora).
- **Aritmética por SQL, narrativa por el modelo.** La analítica usa intents
  cerrados sobre `stats_service` (`analytics.py`); el modelo solo narra.
- **Motor LLM intercambiable.** `llm/` con interfaz `LLMClient`; DeepSeek por
  defecto, Claude listo para activar. Cambiar de proveedor = cambiar env.

## Endpoints (`/api/v1/agente`)
| Método | Ruta | Descripción |
|---|---|---|
| GET  | `/health` | Estado (LLM configurado, store, nº documentos) |
| POST | `/chat` | Pregunta → respuesta con `fuentes[]` citadas |
| POST | `/chat/stream` | Igual, en streaming SSE |
| POST | `/classify` | Clasifica un reporte; detecta emergencias |
| POST | `/analytics` | Métricas por intent (o consulta NL) |
| POST | `/actions/prepare` | Propone una acción (no ejecuta) |
| POST | `/actions/confirm` | Ejecuta la acción confirmada + auditoría |
| POST | `/ingest` | Carga documentos (solo admin) |

Todos exigen `Authorization: Bearer <JWT>` del backend.

## Configuración (`.env`, ver `.env.example`)
```dotenv
LLM_PROVIDER=deepseek          # deepseek | anthropic | fake
DEEPSEEK_API_KEY=              # pega tu key
EMBEDDING_PROVIDER=local       # local (sentence-transformers) | fake
VECTOR_DB_PATH=./data/chroma
KNOWLEDGE_PATH=./data/seed/knowledge
```
El `docker-compose.yml` arranca en modo demo con `LLM_PROVIDER=fake` y
`EMBEDDING_PROVIDER=fake` (deterministas, sin key ni red). Para producción:
`LLM_PROVIDER=deepseek` + `DEEPSEEK_API_KEY` y `EMBEDDING_PROVIDER=local`
(requiere `sentence-transformers`, que descarga el modelo MiniLM la primera vez).

## Puesta en marcha
```bash
docker compose up -d
docker exec ptc-alcaldias-backend-backend-1 alembic upgrade head          # tablas agente_*
docker exec ptc-alcaldias-backend-backend-1 python scripts/ingest_knowledge.py  # documentos demo
```

Ejemplo de chat:
```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"fernando.mercado@mcontreras.gob.mx","password":"mc-admin.2026"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s -X POST localhost:8000/api/v1/agente/chat -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"mensaje":"¿cuál es el SLA de bacheo?"}'
```

## Tests
```bash
docker exec -w /app ptc-alcaldias-backend-backend-1 python -m pytest tests/ -q
```
`tests/test_permissions.py` (filtrado por permisos) es la suite crítica y
bloqueante. `tests/test_endpoints.py` es el E2E HTTP (auth + aislamiento por rol).

## Mapa de roles
El sistema real tiene `admin` y `director_area`; se mapean al modelo conceptual:
`admin → administrador` (alcance global del tenant, niveles publico/interno/ejecutivo)
y `director_area → director` (solo sus áreas, niveles publico/interno). El nivel
`reservado` requiere `users.puede_ver_reservado = true`.
