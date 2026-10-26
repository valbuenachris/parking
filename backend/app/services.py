"""Reglas de negocio del parqueadero: cálculo de tiempo y tarifa."""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from .models import Tarifa

FORMATO_FECHA = "%Y-%m-%dT%H:%M:%S"


def ahora_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _parsear(valor: str) -> datetime:
    return datetime.fromisoformat(valor)


def minutos_transcurridos(entrada: str, salida: str) -> int:
    """Minutos completos entre dos marcas ISO. Nunca devuelve negativos."""
    delta = _parsear(salida) - _parsear(entrada)
    return max(0, int(delta.total_seconds() // 60))


def calcular_total(minutos: int, tarifa: Tarifa) -> float:
    """Cobra por fracción: cualquier fracción iniciada se cobra completa.

    La fracción mínima es 1 minuto, de modo que una estancia de 0 minutos
    también genera un cobro por la primera fracción.
    """
    fraccion = max(1, tarifa.fraccion_minutos)
    fracciones = max(1, -(-max(1, minutos) // fraccion))
    total = Decimal(str(tarifa.valor_hora)) * Decimal(fracciones) * Decimal(fraccion) / Decimal(60)
    return float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def cotizar(
    entrada: str, salida: Optional[str], tarifa: Tarifa
) -> tuple[int, float]:
    """Devuelve (minutos, total) para un ticket abierto o cerrado."""
    if salida is None:
        return 0, 0.0
    minutos = minutos_transcurridos(entrada, salida)
    return minutos, calcular_total(minutos, tarifa)
