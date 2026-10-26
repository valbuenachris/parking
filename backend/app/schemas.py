"""Esquemas de entrada/salida de la API."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_serializer

TipoVehiculo = Literal["auto", "moto", "camioneta"]


def _serializar_monto(valor: Decimal) -> str:
    """Serializa un monto como cadena decimal ("1234.56").

    Se evita el ``float`` para no perder precisión: el cliente recibe el monto
    exacto y decide cómo formatearlo.
    """
    return str(valor.quantize(Decimal("0.01")))


class TarifaIn(BaseModel):
    tipo_vehiculo: TipoVehiculo
    valor_hora: Decimal = Field(gt=0)
    fraccion_minutos: int = Field(default=60, ge=1, le=1440)


class TarifaOut(TarifaIn):
    @field_serializer("valor_hora")
    def _valor_hora(self, valor: Decimal) -> str:
        return _serializar_monto(valor)


class IngresoIn(BaseModel):
    placa: str = Field(min_length=2, max_length=12, pattern=r"^[A-Za-z0-9-]+$")
    tipo_vehiculo: TipoVehiculo


class TicketOut(BaseModel):
    id: int
    placa: str
    tipo_vehiculo: str
    hora_entrada: str
    hora_salida: Optional[str] = None
    valor_cobrado: Optional[Decimal] = None

    @field_serializer("valor_cobrado")
    def _valor_cobrado(self, valor: Optional[Decimal]) -> Optional[str]:
        return None if valor is None else _serializar_monto(valor)


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
    valor_hora: Decimal
    total: Decimal
    creada_en: str

    @field_serializer("valor_hora", "total")
    def _montos(self, valor: Decimal) -> str:
        return _serializar_monto(valor)


class ResumenOut(BaseModel):
    desde: str
    hasta: str
    tickets_cerrados: int
    facturado_total: Decimal
    por_tipo: dict[str, Decimal]

    @field_serializer("facturado_total")
    def _facturado_total(self, valor: Decimal) -> str:
        return _serializar_monto(valor)

    @field_serializer("por_tipo")
    def _por_tipo(self, valor: dict[str, Decimal]) -> dict[str, str]:
        return {tipo: _serializar_monto(monto) for tipo, monto in valor.items()}


SalidaOut.model_rebuild()
