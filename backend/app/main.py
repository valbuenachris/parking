"""Aplicación FastAPI del parqueadero."""

from __future__ import annotations

import ipaddress
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
# dejar fijado un host que aún no sirve TLS. En desarrollo el valor por defecto
# es corto (max-age=300) para no dejar fijado un host de prueba durante un año;
# en producción se usa un max-age largo. El valor se puede forzar con
# PARQUEADERO_HSTS y el entorno se declara con PARQUEADERO_ENTORNO.
HSTS_DESARROLLO = "max-age=300"
HSTS_PRODUCCION = "max-age=31536000; includeSubDomains"

ENTORNOS_PRODUCCION = {"produccion", "production"}

ORIGENES_POR_DEFECTO = "https://localhost,http://localhost:5173"

# Subredes de proxies de confianza. Solo si la conexión llega directamente desde
# una de estas redes se acepta la cabecera X-Forwarded-For; así un cliente que la
# falsifique desde fuera no puede falsear su IP ante el limitador.
PROXIES_POR_DEFECTO = "172.28.0.0/16"


def en_produccion() -> bool:
    """Indica si el despliegue se declara como producción (PARQUEADERO_ENTORNO)."""
    return os.environ.get("PARQUEADERO_ENTORNO", "").strip().lower() in ENTORNOS_PRODUCCION


def valor_hsts() -> str:
    """Valor de la cabecera HSTS (variable PARQUEADERO_HSTS)."""
    configurado = os.environ.get("PARQUEADERO_HSTS", "").strip()
    if configurado:
        return configurado
    return HSTS_PRODUCCION if en_produccion() else HSTS_DESARROLLO


def origenes_permitidos() -> list[str]:
    """Orígenes permitidos por CORS (variable PARQUEADERO_ORIGENES)."""
    bruto = os.environ.get("PARQUEADERO_ORIGENES", ORIGENES_POR_DEFECTO)
    return [origen.strip() for origen in bruto.split(",") if origen.strip()]


def _redes_de_confianza() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Subredes declaradas como proxies de confianza (PARQUEADERO_PROXIES)."""
    bruto = os.environ.get("PARQUEADERO_PROXIES", PROXIES_POR_DEFECTO)
    redes: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for parte in bruto.split(","):
        parte = parte.strip()
        if not parte:
            continue
        try:
            redes.append(ipaddress.ip_network(parte, strict=False))
        except ValueError:
            continue
    return redes


def _como_ip(host: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not host:
        return None
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def clave_cliente(request: Request) -> str:
    """IP real del cliente para el límite de tasa.

    Detrás del proxy de nginx la conexión directa llega desde la red interna de
    Compose, así que la IP real viaja en ``X-Forwarded-For``. Esa cabecera la
    puede falsificar el cliente, de modo que **solo se acepta si la conexión
    directa proviene de una subred de confianza** (``PARQUEADERO_PROXIES``); en
    caso contrario se usa ``request.client.host`` (el peer TCP real). Así una
    petición que llegue directamente con una ``X-Forwarded-For`` forjada no
    consigue cambiar la clave del limitador.
    """
    peer = request.client.host if request.client else None
    ip_peer = _como_ip(peer)
    es_proxy_confiable = ip_peer is not None and any(
        ip_peer in red for red in _redes_de_confianza()
    )
    if es_proxy_confiable:
        reenviada = request.headers.get("X-Forwarded-For")
        if reenviada:
            saltos = [salto.strip() for salto in reenviada.split(",") if salto.strip()]
            if saltos:
                return saltos[-1]
        real = request.headers.get("X-Real-IP")
        if real:
            return real.strip()
    return peer or "desconocido"


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
