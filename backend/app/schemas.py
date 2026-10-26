"""Esquemas de entrada/salida de la API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

TipoVehiculo = Literal["auto", "moto", "camioneta"]


class TarifaIn(BaseModel):
    tipo_vehiculo: TipoVehiculo
    valor_hora: float = Field(gt=0)
    fraccion_minutos: int = Field(default=60, ge=1, le=1440)


class TarifaOut(TarifaIn):
    pass


class IngresoIn(BaseModel):
    placa: str = Field(min_length=2, max_length=12, pattern=r"^[A-Za-z0-9-]+$")
    tipo_vehiculo: TipoVehiculo


class TicketOut(BaseModel):
    id: int
    placa: str
    tipo_vehiculo: str
    hora_entrada: str
    hora_salida: Optional[str] = None
    valor_cobrado: Optional[float] = None


class SalidaOut(BaseModel):
    factura: "FacturaOut"
    ticket: TicketOut


class FacturaOut(BaseModel):
    id: int
    ticket_id: int
    placa: str
    tipo_vehiculo: str
    hora_entrada: str
    hora_salida: str
    minutos: int
    valor_hora: float
    total: float
    creada_en: str


class ResumenOut(BaseModel):
    desde: str
    hasta: str
    tickets_cerrados: int
    facturado_total: float
    por_tipo: dict[str, float]


SalidaOut.model_rebuild()
