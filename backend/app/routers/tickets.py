"""Endpoints de ingresos, salidas y consulta de tickets."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..database import conexion
from ..models import Tarifa
from ..schemas import FacturaOut, IngresoIn, SalidaOut, TicketOut
from ..seguridad import requiere_token
from ..services import ahora_iso, centavos_a_decimal, cotizar, decimal_a_centavos

router = APIRouter(
    prefix="/api/tickets", tags=["tickets"], dependencies=[Depends(requiere_token)]
)


def _fila_a_ticket(fila) -> TicketOut:
    centavos = fila["valor_cobrado_centavos"]
    return TicketOut(
        id=fila["id"],
        placa=fila["placa"],
        tipo_vehiculo=fila["tipo_vehiculo"],
        hora_entrada=fila["hora_entrada"],
        hora_salida=fila["hora_salida"],
        valor_cobrado=None if centavos is None else centavos_a_decimal(centavos),
    )


def _fila_a_factura(fila) -> FacturaOut:
    return FacturaOut(
        id=fila["id"],
        ticket_id=fila["ticket_id"],
        placa=fila["placa"],
        tipo_vehiculo=fila["tipo_vehiculo"],
        hora_entrada=fila["hora_entrada"],
        hora_salida=fila["hora_salida"],
        minutos=fila["minutos"],
        valor_hora=centavos_a_decimal(fila["valor_hora_centavos"]),
        total=centavos_a_decimal(fila["total_centavos"]),
        creada_en=fila["creada_en"],
    )


def _obtener_tarifa(db, tipo_vehiculo: str) -> Tarifa:
    fila = db.execute(
        "SELECT tipo_vehiculo, valor_hora_centavos, fraccion_minutos "
        "FROM tarifas WHERE tipo_vehiculo = ?",
        (tipo_vehiculo,),
    ).fetchone()
    if fila is None:
        raise HTTPException(status_code=400, detail=f"Sin tarifa para '{tipo_vehiculo}'")
    return Tarifa(
        tipo_vehiculo=fila["tipo_vehiculo"],
        valor_hora=centavos_a_decimal(fila["valor_hora_centavos"]),
        fraccion_minutos=fila["fraccion_minutos"],
    )


@router.post("/ingresos", response_model=TicketOut, status_code=201)
def registrar_ingreso(datos: IngresoIn) -> TicketOut:
    placa = datos.placa.upper()
    with conexion() as db:
        _obtener_tarifa(db, datos.tipo_vehiculo)
        abierto = db.execute(
            "SELECT id FROM tickets WHERE placa = ? AND hora_salida IS NULL", (placa,)
        ).fetchone()
        if abierto is not None:
            raise HTTPException(status_code=409, detail=f"El vehículo {placa} ya está dentro")
        try:
            cursor = db.execute(
                "INSERT INTO tickets (placa, tipo_vehiculo, hora_entrada) VALUES (?, ?, ?)",
                (placa, datos.tipo_vehiculo, ahora_iso()),
            )
        except sqlite3.IntegrityError as exc:
            # El índice único parcial detecta una carrera entre dos ingresos
            # simultáneos de la misma placa que pasaron la comprobación previa.
            raise HTTPException(
                status_code=409, detail=f"El vehículo {placa} ya está dentro"
            ) from exc
        fila = db.execute("SELECT * FROM tickets WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _fila_a_ticket(fila)


@router.post("/{ticket_id}/salida", response_model=SalidaOut)
def registrar_salida(ticket_id: int) -> SalidaOut:
    with conexion() as db:
        fila = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if fila is None:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")
        if fila["hora_salida"] is not None:
            raise HTTPException(status_code=409, detail="El ticket ya fue cerrado")

        tarifa = _obtener_tarifa(db, fila["tipo_vehiculo"])
        salida = ahora_iso()
        minutos, total = cotizar(fila["hora_entrada"], salida, tarifa)

        db.execute(
            "UPDATE tickets SET hora_salida = ?, valor_cobrado_centavos = ? WHERE id = ?",
            (salida, decimal_a_centavos(total), ticket_id),
        )
        cursor = db.execute(
            """
            INSERT INTO facturas
                (ticket_id, placa, tipo_vehiculo, hora_entrada, hora_salida,
                 minutos, valor_hora_centavos, total_centavos, creada_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                fila["placa"],
                fila["tipo_vehiculo"],
                fila["hora_entrada"],
                salida,
                minutos,
                decimal_a_centavos(tarifa.valor_hora),
                decimal_a_centavos(total),
                salida,
            ),
        )
        ticket_final = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        factura = db.execute("SELECT * FROM facturas WHERE id = ?", (cursor.lastrowid,)).fetchone()

    return SalidaOut(factura=_fila_a_factura(factura), ticket=_fila_a_ticket(ticket_final))


@router.get("/activos", response_model=list[TicketOut])
def listar_activos() -> list[TicketOut]:
    with conexion() as db:
        filas = db.execute(
            "SELECT * FROM tickets WHERE hora_salida IS NULL ORDER BY hora_entrada"
        ).fetchall()
    return [_fila_a_ticket(fila) for fila in filas]


@router.get("/{ticket_id}", response_model=TicketOut)
def obtener_ticket(ticket_id: int) -> TicketOut:
    with conexion() as db:
        fila = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if fila is None:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return _fila_a_ticket(fila)
