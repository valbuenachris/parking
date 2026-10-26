"""Endpoints de facturas e informes del negocio."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..database import conexion
from ..schemas import FacturaOut, ResumenOut

router = APIRouter(prefix="/api", tags=["informes"])


@router.get("/facturas", response_model=list[FacturaOut])
def listar_facturas(
    desde: str | None = Query(default=None, description="Fecha ISO inicial"),
    hasta: str | None = Query(default=None, description="Fecha ISO final"),
) -> list[FacturaOut]:
    consulta = "SELECT * FROM facturas WHERE 1 = 1"
    parametros: list[str] = []
    if desde:
        consulta += " AND hora_salida >= ?"
        parametros.append(desde)
    if hasta:
        consulta += " AND hora_salida <= ?"
        parametros.append(hasta)
    consulta += " ORDER BY hora_salida DESC"
    with conexion() as db:
        filas = db.execute(consulta, parametros).fetchall()
    return [FacturaOut(**dict(fila)) for fila in filas]


@router.get("/informes/resumen", response_model=ResumenOut)
def resumen(
    desde: str = Query(..., description="Fecha ISO inicial"),
    hasta: str = Query(..., description="Fecha ISO final"),
) -> ResumenOut:
    with conexion() as db:
        filas = db.execute(
            """
            SELECT tipo_vehiculo, COUNT(*) AS cantidad, COALESCE(SUM(total), 0) AS total
            FROM facturas
            WHERE hora_salida BETWEEN ? AND ?
            GROUP BY tipo_vehiculo
            """,
            (desde, hasta),
        ).fetchall()

    por_tipo = {fila["tipo_vehiculo"]: round(float(fila["total"]), 2) for fila in filas}
    tickets = sum(int(fila["cantidad"]) for fila in filas)
    facturado = round(sum(float(fila["total"]) for fila in filas), 2)
    return ResumenOut(
        desde=desde, hasta=hasta, tickets_cerrados=tickets, facturado_total=facturado, por_tipo=por_tipo
    )
