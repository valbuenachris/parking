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
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-XSS-Protection": "0",
}

# HSTS solo tiene sentido sobre HTTPS: enviarlo en HTTP no surte efecto y puede
# dejar fijado un host que aún no sirve TLS. El valor es configurable para poder
# subir el max-age con cuidado y probarlo con uno corto antes de publicar.
HSTS_POR_DEFECTO = "max-age=31536000; includeSubDomains"

ORIGENES_POR_DEFECTO = "https://localhost,http://localhost:5173"


def valor_hsts() -> str:
    """Valor de la cabecera HSTS (variable PARQUEADERO_HSTS)."""
    return os.environ.get("PARQUEADERO_HSTS", HSTS_POR_DEFECTO).strip() or HSTS_POR_DEFECTO


def origenes_permitidos() -> list[str]:
    """Orígenes permitidos por CORS (variable PARQUEADERO_ORIGENES)."""
    bruto = os.environ.get("PARQUEADERO_ORIGENES", ORIGENES_POR_DEFECTO)
    return [origen.strip() for origen in bruto.split(",") if origen.strip()]


def clave_cliente(request: Request) -> str:
    """IP real del cliente para el límite de tasa.

    Detrás del proxy de nginx la conexión llega desde la red interna, así que la
    IP real viaja en ``X-Forwarded-For`` o ``X-Real-IP``. Un cliente puede
    falsificar la cabecera, así que solo se confía en el **último** salto (lo
    añade el proxy de confianza); nginx la reescribe además con ``$remote_addr``.
    Con ``--proxy-headers`` uvicorn ya reescribe ``request.client``, pero se
    prefiere la cabecera para no depender de esa bandera.
    """
    reenviada = request.headers.get("X-Forwarded-For")
    if reenviada:
        saltos = [salto.strip() for salto in reenviada.split(",") if salto.strip()]
        if saltos:
            return saltos[-1]
    real = request.headers.get("X-Real-IP")
    if real:
        return real.strip()
    return request.client.host if request.client else "desconocido"


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
        clave = clave_cliente(request)
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
    # HSTS solo si esta app termina el TLS. Detrás del proxy (cabecera
    # X-Forwarded-Proto presente) lo añade nginx, que es quien cifra.
    if request.url.scheme == "https" and not request.headers.get("X-Forwarded-Proto"):
        respuesta.headers.setdefault("Strict-Transport-Security", valor_hsts())
    return respuesta


app.include_router(tarifas_router)
app.include_router(tickets_router)
app.include_router(informes_router)


@app.get("/api/salud", tags=["sistema"])
def salud() -> dict[str, str]:
    return {"estado": "ok"}
