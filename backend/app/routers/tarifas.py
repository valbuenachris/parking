"""Endpoints de tarifas por tipo de vehículo."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..database import conexion
from ..schemas import TarifaIn, TarifaOut
from ..services import centavos_a_decimal, decimal_a_centavos

router = APIRouter(prefix="/api/tarifas", tags=["tarifas"])


@router.get("", response_model=list[TarifaOut])
def listar_tarifas() -> list[TarifaOut]:
    with conexion() as db:
        filas = db.execute(
            "SELECT tipo_vehiculo, valor_hora_centavos, fraccion_minutos "
            "FROM tarifas ORDER BY tipo_vehiculo"
        ).fetchall()
    return [
        TarifaOut(
            tipo_vehiculo=fila["tipo_vehiculo"],
            valor_hora=centavos_a_decimal(fila["valor_hora_centavos"]),
            fraccion_minutos=fila["fraccion_minutos"],
        )
        for fila in filas
    ]


@router.put("/{tipo_vehiculo}", response_model=TarifaOut)
def guardar_tarifa(tipo_vehiculo: str, datos: TarifaIn) -> TarifaOut:
    if tipo_vehiculo != datos.tipo_vehiculo:
        raise HTTPException(status_code=400, detail="El tipo de vehículo no coincide con la ruta")
    with conexion() as db:
        db.execute(
            """
            INSERT INTO tarifas (tipo_vehiculo, valor_hora_centavos, fraccion_minutos)
            VALUES (?, ?, ?)
            ON CONFLICT(tipo_vehiculo) DO UPDATE SET
                valor_hora_centavos = excluded.valor_hora_centavos,
                fraccion_minutos = excluded.fraccion_minutos
            """,
            (
                datos.tipo_vehiculo,
                decimal_a_centavos(datos.valor_hora),
                datos.fraccion_minutos,
            ),
        )
    return TarifaOut(**datos.model_dump())
