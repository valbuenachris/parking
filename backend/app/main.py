"""Aplicación FastAPI del parqueadero."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import limites
from .database import inicializar
from .routers import informes_router, tarifas_router, tickets_router

CABECERAS_SEGURIDAD = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-XSS-Protection": "0",
}

ORIGENES_POR_DEFECTO = "http://localhost:8080,http://localhost:5173"


def origenes_permitidos() -> list[str]:
    """Orígenes permitidos por CORS (variable PARQUEADERO_ORIGENES)."""
    bruto = os.environ.get("PARQUEADERO_ORIGENES", ORIGENES_POR_DEFECTO)
    return [origen.strip() for origen in bruto.split(",") if origen.strip()]


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    inicializar()
    yield


app = FastAPI(
    title="Parqueadero",
    description="Gestión minimalista de entradas, salidas, tarifas, facturas e informes.",
    version="0.3.0",
    lifespan=ciclo_de_vida,
)

# El orden importa: el último middleware añadido queda más al exterior, de modo
# que la respuesta pase por cabeceras -> CORS -> límite de tasa -> rutas.
@app.middleware("http")
async def limitar_tasa(request: Request, call_next):
    maximo, ventana = limites.configuracion()
    if maximo > 0 and request.url.path.startswith("/api"):
        clave = request.client.host if request.client else "desconocido"
        permitido, espera = limites.permitir(clave, maximo, ventana)
        if not permitido:
            return JSONResponse(
                status_code=429,
                content={"detail": "Demasiadas peticiones; inténtalo más tarde"},
                headers={"Retry-After": str(max(1, int(espera + 0.999)))},
            )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=origenes_permitidos(),
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)


@app.middleware("http")
async def agregar_cabeceras_seguridad(request: Request, call_next):
    respuesta = await call_next(request)
    for nombre, valor in CABECERAS_SEGURIDAD.items():
        respuesta.headers.setdefault(nombre, valor)
    return respuesta


app.include_router(tarifas_router)
app.include_router(tickets_router)
app.include_router(informes_router)


@app.get("/api/salud", tags=["sistema"])
def salud() -> dict[str, str]:
    return {"estado": "ok"}
