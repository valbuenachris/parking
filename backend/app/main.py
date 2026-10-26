"""Aplicación FastAPI del parqueadero."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import inicializar
from .routers import informes_router, tarifas_router, tickets_router


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    inicializar()
    yield


app = FastAPI(
    title="Parqueadero",
    description="Gestión minimalista de entradas, salidas, tarifas, facturas e informes.",
    version="0.2.0",
    lifespan=ciclo_de_vida,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tarifas_router)
app.include_router(tickets_router)
app.include_router(informes_router)


@app.get("/api/salud", tags=["sistema"])
def salud() -> dict[str, str]:
    return {"estado": "ok"}
