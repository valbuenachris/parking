"""Modelos de dominio (dataclasses) compartidos por la API."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class Tarifa:
    tipo_vehiculo: str
    valor_hora: Decimal
    fraccion_minutos: int


@dataclass(frozen=True)
class Ticket:
    id: int
    placa: str
    tipo_vehiculo: str
    hora_entrada: str
    hora_salida: Optional[str]
    valor_cobrado: Optional[Decimal]

    @property
    def activo(self) -> bool:
        return self.hora_salida is None


@dataclass(frozen=True)
class Factura:
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
