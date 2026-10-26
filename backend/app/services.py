"""Reglas de negocio del parqueadero: cálculo de tiempo y tarifa.

Todas las fechas se manejan en UTC y de forma *tz-aware*. El dinero se calcula
con ``Decimal`` y se persiste como enteros (centavos) para evitar errores de
coma flotante.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from .models import Tarifa

CENTAVOS = Decimal("0.01")


def ahora() -> datetime:
    """Momento actual en UTC, sin microsegundos y con zona horaria."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def ahora_iso() -> str:
    return ahora().isoformat()


def parsear_fecha(valor: str) -> datetime:
    """Convierte una marca ISO a ``datetime`` UTC tz-aware.

    Rechaza valores vacíos, mal formados o sin zona horaria. Acepta el sufijo
    ``Z`` (equivalente a ``+00:00``).
    """
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError("La fecha es obligatoria y debe ser una cadena ISO")
    try:
        fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Fecha inválida: {valor!r}") from exc
    if fecha.tzinfo is None or fecha.utcoffset() is None:
        raise ValueError(
            f"La fecha {valor!r} debe incluir zona horaria (p. ej. +00:00 o Z)"
        )
    return fecha.astimezone(timezone.utc)


def normalizar_iso(valor: str) -> str:
    """Devuelve la marca ISO normalizada a UTC (sin microsegundos)."""
    return parsear_fecha(valor).replace(microsecond=0).isoformat()


def minutos_transcurridos(entrada: str, salida: str) -> int:
    """Minutos completos entre dos marcas ISO. Nunca devuelve negativos."""
    delta = parsear_fecha(salida) - parsear_fecha(entrada)
    return max(0, int(delta.total_seconds() // 60))


def calcular_total(minutos: int, tarifa: Tarifa) -> Decimal:
    """Cobra por fracción: cualquier fracción iniciada se cobra completa.

    La fracción mínima es 1 minuto, de modo que una estancia de 0 minutos
    también genera un cobro por la primera fracción.
    """
    fraccion = max(1, tarifa.fraccion_minutos)
    fracciones = max(1, -(-max(1, minutos) // fraccion))
    total = tarifa.valor_hora * Decimal(fracciones) * Decimal(fraccion) / Decimal(60)
    return total.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def cotizar(entrada: str, salida: Optional[str], tarifa: Tarifa) -> tuple[int, Decimal]:
    """Devuelve (minutos, total) para un ticket abierto o cerrado."""
    if salida is None:
        return 0, Decimal("0.00")
    minutos = minutos_transcurridos(entrada, salida)
    return minutos, calcular_total(minutos, tarifa)


def decimal_a_centavos(valor: Decimal) -> int:
    """Convierte un monto en pesos a centavos enteros."""
    return int((valor * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def centavos_a_decimal(centavos: int) -> Decimal:
    """Convierte centavos enteros a un monto ``Decimal`` con dos decimales.

    Se usa ``ROUND_HALF_UP`` igual que en el resto del cálculo de dinero.
    """
    return (Decimal(centavos) / 100).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
