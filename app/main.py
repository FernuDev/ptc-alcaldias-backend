from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.agente.llm.base import LLMError
from app.core.config import settings
from app.core.database import engine
from app.core.security import limiter
from app.routers import (
    agente,
    audit,
    auth,
    campo_me,
    categorias,
    cierres,
    civico,
    colonias,
    config,
    contratistas,
    cuadrillas,
    documentos,
    ejecutivo,
    exports,
    financiero,
    health,
    mensajes,
    monitor,
    notificaciones,
    obras,
    org,
    plania,
    publico,
    reportes,
    reportes_ia,
    scorecards,
    stats,
    tareas,
    tenants,
    turnos,
    ubicacion,
    uploads,
    users,
)

# Placeholder value shipped in config.py / .env.example — must never reach prod.
_JWT_SECRET_PLACEHOLDER = "change-me-to-a-random-64-char-string"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup guard: fuera de desarrollo, nunca arrancar con el secreto JWT
    # placeholder o vacío — firmaría tokens trivialmente falsificables.
    if settings.APP_ENV != "development" and (
        not settings.JWT_SECRET_KEY
        or settings.JWT_SECRET_KEY == _JWT_SECRET_PLACEHOLDER
    ):
        raise RuntimeError(
            "JWT_SECRET_KEY no está configurado para un entorno no-development "
            f"(APP_ENV={settings.APP_ENV!r}). Define una clave aleatoria de al "
            "menos 64 caracteres en la variable de entorno JWT_SECRET_KEY antes "
            "de arrancar."
        )
    yield
    await engine.dispose()


app = FastAPI(
    title="PTC Alcaldias API",
    description="Backend para la Plataforma Ciudadana de alcaldias CDMX",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    # Fallo del motor LLM (saldo, red, autenticación): respuesta clara, no 500.
    return JSONResponse(
        status_code=502,
        content={"detail": f"El motor LLM no está disponible: {exc}"},
    )


# Security headers middleware
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.APP_ENV != "development":
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
    return response


# Mount all routers under /api/v1
PREFIX = "/api/v1"

app.include_router(health.router, prefix=PREFIX)
app.include_router(auth.router, prefix=PREFIX)
app.include_router(users.router, prefix=PREFIX)
app.include_router(tenants.router, prefix=PREFIX)
app.include_router(categorias.router, prefix=PREFIX)
app.include_router(colonias.router, prefix=PREFIX)
app.include_router(cuadrillas.router, prefix=PREFIX)
app.include_router(contratistas.router, prefix=PREFIX)
app.include_router(reportes.router, prefix=PREFIX)
app.include_router(reportes_ia.router, prefix=PREFIX)
app.include_router(obras.router, prefix=PREFIX)
app.include_router(stats.router, prefix=PREFIX)
app.include_router(scorecards.router, prefix=PREFIX)
app.include_router(financiero.router, prefix=PREFIX)
app.include_router(notificaciones.router, prefix=PREFIX)
app.include_router(exports.router, prefix=PREFIX)
app.include_router(audit.router, prefix=PREFIX)
app.include_router(agente.router, prefix=PREFIX)
app.include_router(civico.router, prefix=PREFIX)
app.include_router(ejecutivo.router, prefix=PREFIX)
app.include_router(uploads.router, prefix=PREFIX)
app.include_router(documentos.router, prefix=PREFIX)
app.include_router(publico.router, prefix=PREFIX)
app.include_router(plania.router, prefix=PREFIX)
app.include_router(org.router, prefix=PREFIX)
app.include_router(config.router, prefix=PREFIX)
app.include_router(cierres.router, prefix=PREFIX)
app.include_router(mensajes.router, prefix=PREFIX)
app.include_router(monitor.router, prefix=PREFIX)
app.include_router(tareas.router, prefix=PREFIX)
app.include_router(turnos.router, prefix=PREFIX)
app.include_router(ubicacion.router, prefix=PREFIX)
app.include_router(campo_me.router, prefix=PREFIX)
