FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Instalar PyTorch CPU-only primero (~200 MB en vez de ~900 MB con CUDA).
# Esta capa se cachea independientemente y rara vez cambia.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml .
RUN pip install --no-cache-dir .

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

# El paquete `app` vive en /app; necesario para que `alembic` (env.py importa
# app.core.config) y cualquier herramienta resuelvan los imports.
ENV PYTHONPATH=/app

EXPOSE 8000

# Arranque:
#  1. Migraciones BLOQUEANTES (schema listo antes de servir). Si fallan, aborta
#     el deploy (esquema incorrecto = no arrancar). `python -m alembic` mete el
#     cwd (/app) al sys.path aunque PYTHONPATH no estuviera.
#  2. Seed idempotente (seed.py + seed_org.py) en SEGUNDO PLANO. Converge los
#     datos demo (todos los tenants) sin bloquear el arranque: uvicorn liga el
#     puerto de inmediato, así el healthcheck de Railway no mata el deploy a
#     mitad del seed (lo que dejó datos parciales antes). Idempotente
#     (ON CONFLICT), así que re-sembrar en cada deploy es seguro. Sus logs van
#     al stdout del contenedor (visibles en Railway).
#  3. uvicorn como proceso principal (exec → PID 1).
CMD ["sh", "-c", "python -m alembic upgrade head || exit 1; { python scripts/seed.py && python scripts/seed_org.py; } & exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
