"""Capa de persistencia mínima sobre SQLite (sin ORM).

El parqueadero es un negocio pequeño: un único archivo SQLite es suficiente y
mantiene el despliegue trivial dentro de un contenedor. La ruta se controla con
la variable de entorno PARQUEADERO_DB.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_PATH = os.environ.get(
    "PARQUEADERO_DB",
    str(Path(__file__).resolve().parent.parent / "parqueadero.db"),
)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS tarifas (
    tipo_vehiculo TEXT PRIMARY KEY,
    valor_hora REAL NOT NULL,
    fraccion_minutos INTEGER NOT NULL DEFAULT 60
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    placa TEXT NOT NULL,
    tipo_vehiculo TEXT NOT NULL,
    hora_entrada TEXT NOT NULL,
    hora_salida TEXT,
    valor_cobrado REAL,
    FOREIGN KEY (tipo_vehiculo) REFERENCES tarifas (tipo_vehiculo)
);

CREATE TABLE IF NOT EXISTS facturas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL UNIQUE,
    placa TEXT NOT NULL,
    tipo_vehiculo TEXT NOT NULL,
    hora_entrada TEXT NOT NULL,
    hora_salida TEXT NOT NULL,
    minutos INTEGER NOT NULL,
    valor_hora REAL NOT NULL,
    total REAL NOT NULL,
    creada_en TEXT NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets (id)
);
"""


def _conectar() -> sqlite3.Connection:
    conexion = sqlite3.connect(DB_PATH)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


def inicializar() -> None:
    """Crea el esquema y siembra tarifas por defecto si no existen."""
    with _conectar() as conexion:
        conexion.executescript(ESQUEMA)
        existentes = conexion.execute("SELECT COUNT(*) FROM tarifas").fetchone()[0]
        if existentes == 0:
            conexion.executemany(
                "INSERT INTO tarifas (tipo_vehiculo, valor_hora, fraccion_minutos) VALUES (?, ?, ?)",
                [("auto", 5000.0, 60), ("moto", 3000.0, 60), ("camioneta", 7000.0, 60)],
            )


@contextmanager
def conexion() -> Iterator[sqlite3.Connection]:
    conexion_abierta = _conectar()
    try:
        yield conexion_abierta
        conexion_abierta.commit()
    except Exception:
        conexion_abierta.rollback()
        raise
    finally:
        conexion_abierta.close()
