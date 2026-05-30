from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine
from app.routers import (
    audit,
    auth,
    categorias,
    colonias,
    contratistas,
    cuadrillas,
    exports,
    health,
    notificaciones,
    obras,
    reportes,
    stats,
    tenants,
    users,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="PTC Alcaldias API",
    description="Backend para la Plataforma Ciudadana de alcaldias CDMX",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
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
app.include_router(obras.router, prefix=PREFIX)
app.include_router(stats.router, prefix=PREFIX)
app.include_router(notificaciones.router, prefix=PREFIX)
app.include_router(exports.router, prefix=PREFIX)
app.include_router(audit.router, prefix=PREFIX)
