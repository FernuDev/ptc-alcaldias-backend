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

# Aplica migraciones pendientes antes de arrancar (idempotente: si no hay
# pendientes, no hace nada). Así el esquema de la BD siempre coincide con el
# código desplegado. Las migraciones son aditivas (tablas/columnas nuevas).
# Se usa `python -m alembic` (no el script `alembic`) para que el cwd (/app)
# entre al sys.path aunque PYTHONPATH no estuviera.
CMD ["sh", "-c", "python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
