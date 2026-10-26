"""Límite de tasa sencillo en memoria (ventana deslizante).

No usa dependencias externas: basta para un despliegue de un solo proceso. Con
varias réplicas cada una mantiene su propio contador, así que para un límite
global haría falta un almacén compartido (p. ej. Redis).

El límite se configura con ``PARQUEADERO_RATE_LIMIT`` con el formato
``MAXIMO/VENTANA_SEGUNDOS`` (por ejemplo ``120/60``). Un máximo de 0 desactiva
el límite.
"""

from __future__ import annotations

import os
import threading
import time

LIMITE_POR_DEFECTO = "120/60"

# Cuando el diccionario alcanza este tamaño se barren las claves sin actividad
# reciente, para que no crezca sin límite con IPs que solo aparecen una vez.
UMBRAL_PURGA = 1024

_registros: dict[str, list[float]] = {}
_candado = threading.Lock()


def configuracion() -> tuple[int, int]:
    """Devuelve (máximo de peticiones, ventana en segundos)."""
    bruto = os.environ.get("PARQUEADERO_RATE_LIMIT", LIMITE_POR_DEFECTO)
    try:
        maximo, ventana = bruto.split("/")
        maximo_int, ventana_int = int(maximo), int(ventana)
        if maximo_int < 0 or ventana_int <= 0:
            raise ValueError
        return maximo_int, ventana_int
    except ValueError:
        return 120, 60


def _purgar(momento: float, ventana: int) -> None:
    """Elimina las claves cuya última marca ya salió de la ventana."""
    limite = momento - ventana
    obsoletas = [clave for clave, marcas in _registros.items() if not marcas or marcas[-1] <= limite]
    for clave in obsoletas:
        del _registros[clave]


def permitir(clave: str, maximo: int, ventana: int) -> tuple[bool, float]:
    """Registra un acceso y decide si se permite.

    Devuelve ``(permitido, segundos_de_espera)``. Con ``maximo <= 0`` no limita.
    """
    if maximo <= 0:
        return True, 0.0
    momento = time.monotonic()
    with _candado:
        if len(_registros) >= UMBRAL_PURGA:
            _purgar(momento, ventana)
        marcas = [marca for marca in _registros.get(clave, []) if marca > momento - ventana]
        if len(marcas) >= maximo:
            espera = ventana - (momento - marcas[0])
            _registros[clave] = marcas
            return False, max(0.0, espera)
        marcas.append(momento)
        _registros[clave] = marcas
        return True, 0.0


def reiniciar() -> None:
    """Vacía los contadores (útil en pruebas)."""
    with _candado:
        _registros.clear()
