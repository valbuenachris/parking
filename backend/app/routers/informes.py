"""Endpoints de facturas e informes del negocio."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import conexion
from ..schemas import FacturaOut, ResumenOut
from ..seguridad import requiere_token
from ..services import centavos_a_decimal, normalizar_iso
from .tickets import COLUMNAS_FACTURA, _fila_a_factura

router = APIRouter(prefix="/api", tags=["informes"], dependencies=[Depends(requiere_token)])


def _normalizar(valor: str, nombre: str) -> str:
    """Normaliza una fecha ISO a UTC; responde 422 si es inválida o sin zona."""
    try:
        return normalizar_iso(valor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Parámetro '{nombre}': {exc}") from exc


def _validar_rango(desde: str, hasta: str) -> tuple[str, str]:
    inicio = _normalizar(desde, "desde")
    fin = _normalizar(hasta, "hasta")
    if inicio > fin:
        raise HTTPException(status_code=400, detail="'desde' no puede ser posterior a 'hasta'")
    return inicio, fin


@router.get("/facturas", response_model=list[FacturaOut])
def listar_facturas(
    desde: str | None = Query(default=None, description="Fecha ISO inicial (UTC)"),
    hasta: str | None = Query(default=None, description="Fecha ISO final (UTC)"),
) -> list[FacturaOut]:
    if desde is not None and hasta is not None:
        desde, hasta = _validar_rango(desde, hasta)
    else:
        desde = None if desde is None else _normalizar(desde, "desde")
        hasta = None if hasta is None else _normalizar(hasta, "hasta")
    consulta = f"SELECT {COLUMNAS_FACTURA} FROM facturas WHERE 1 = 1"
    parametros: list[str] = []
    if desde is not None:
        consulta += " AND hora_salida >= ?"
        parametros.append(desde)
    if hasta is not None:
        consulta += " AND hora_salida <= ?"
        parametros.append(hasta)
    consulta += " ORDER BY hora_salida DESC"
    with conexion() as db:
        filas = db.execute(consulta, parametros).fetchall()
    return [_fila_a_factura(fila) for fila in filas]


@router.get("/informes/resumen", response_model=ResumenOut)
def resumen(
    desde: str = Query(..., description="Fecha ISO inicial (UTC)"),
    hasta: str = Query(..., description="Fecha ISO final (UTC)"),
) -> ResumenOut:
    inicio, fin = _validar_rango(desde, hasta)
    with conexion() as db:
        filas = db.execute(
            """
            SELECT tipo_vehiculo, COUNT(*) AS cantidad,
                   COALESCE(SUM(total_centavos), 0) AS total_centavos
            FROM facturas
            WHERE hora_salida BETWEEN ? AND ?
            GROUP BY tipo_vehiculo
            """,
            (inicio, fin),
        ).fetchall()

    por_tipo = {fila["tipo_vehiculo"]: centavos_a_decimal(fila["total_centavos"]) for fila in filas}
    tickets = sum(int(fila["cantidad"]) for fila in filas)
    facturado = centavos_a_decimal(sum(int(fila["total_centavos"]) for fila in filas))
    return ResumenOut(
        desde=inicio, hasta=fin, tickets_cerrados=tickets, facturado_total=facturado, por_tipo=por_tipo
    )
