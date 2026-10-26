"""Capa de persistencia mínima sobre SQLite (sin ORM).

El parqueadero es un negocio pequeño: un único archivo SQLite es suficiente y
mantiene el despliegue trivial dentro de un contenedor. La ruta se controla con
la variable de entorno PARQUEADERO_DB.

El dinero se guarda como enteros en **centavos** para no arrastrar los errores
de la coma flotante. Las fechas se guardan como texto ISO en UTC.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_POR_DEFECTO = str(Path(__file__).resolve().parent.parent / "parqueadero.db")

# Esquema inicial (versión 1). Se mantiene tal cual para poder migrar bases de
# datos creadas antes de introducir el versionado con PRAGMA user_version.
ESQUEMA_V1 = """
CREATE TABLE IF NOT EXISTS tarifas (
    tipo_vehiculo TEXT PRIMARY KEY,
    valor_hora_centavos INTEGER NOT NULL,
    fraccion_minutos INTEGER NOT NULL DEFAULT 60
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    placa TEXT NOT NULL,
    tipo_vehiculo TEXT NOT NULL,
    hora_entrada TEXT NOT NULL,
    hora_salida TEXT,
    valor_cobrado_centavos INTEGER,
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
    valor_hora_centavos INTEGER NOT NULL,
    total_centavos INTEGER NOT NULL,
    creada_en TEXT NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets (id)
);
"""

# Migración a la versión 2: reconstruye las tablas como STRICT, añade CHECK de
# integridad (montos y tiempos no negativos, tarifas positivas) y un índice
# único parcial que impide dos tickets abiertos para la misma placa. Conserva
# los datos existentes copiándolos a tablas temporales antes de reemplazarlas.
MIGRACION_V2 = """
PRAGMA foreign_keys = OFF;
BEGIN;
ALTER TABLE tarifas RENAME TO tarifas_antigua;
ALTER TABLE tickets RENAME TO tickets_antigua;
ALTER TABLE facturas RENAME TO facturas_antigua;

CREATE TABLE tarifas (
    tipo_vehiculo TEXT PRIMARY KEY,
    valor_hora_centavos INTEGER NOT NULL CHECK (valor_hora_centavos > 0),
    fraccion_minutos INTEGER NOT NULL DEFAULT 60
        CHECK (fraccion_minutos BETWEEN 1 AND 1440)
) STRICT;

CREATE TABLE tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    placa TEXT NOT NULL,
    tipo_vehiculo TEXT NOT NULL,
    hora_entrada TEXT NOT NULL,
    hora_salida TEXT,
    valor_cobrado_centavos INTEGER
        CHECK (valor_cobrado_centavos IS NULL OR valor_cobrado_centavos >= 0),
    FOREIGN KEY (tipo_vehiculo) REFERENCES tarifas (tipo_vehiculo)
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS tickets_abiertos_por_placa
    ON tickets (placa) WHERE hora_salida IS NULL;

CREATE TABLE facturas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL UNIQUE,
    placa TEXT NOT NULL,
    tipo_vehiculo TEXT NOT NULL,
    hora_entrada TEXT NOT NULL,
    hora_salida TEXT NOT NULL,
    minutos INTEGER NOT NULL CHECK (minutos >= 0),
    valor_hora_centavos INTEGER NOT NULL CHECK (valor_hora_centavos >= 0),
    total_centavos INTEGER NOT NULL CHECK (total_centavos >= 0),
    creada_en TEXT NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets (id)
) STRICT;

INSERT INTO tarifas (tipo_vehiculo, valor_hora_centavos, fraccion_minutos)
    SELECT tipo_vehiculo, valor_hora_centavos, fraccion_minutos FROM tarifas_antigua;
INSERT INTO tickets (id, placa, tipo_vehiculo, hora_entrada, hora_salida, valor_cobrado_centavos)
    SELECT id, placa, tipo_vehiculo, hora_entrada, hora_salida, valor_cobrado_centavos
    FROM tickets_antigua;
INSERT INTO facturas
    (id, ticket_id, placa, tipo_vehiculo, hora_entrada, hora_salida,
     minutos, valor_hora_centavos, total_centavos, creada_en)
    SELECT id, ticket_id, placa, tipo_vehiculo, hora_entrada, hora_salida,
           minutos, valor_hora_centavos, total_centavos, creada_en
    FROM facturas_antigua;

DROP TABLE facturas_antigua;
DROP TABLE tickets_antigua;
DROP TABLE tarifas_antigua;
COMMIT;
PRAGMA foreign_keys = ON;
"""

# Lista ordenada de migraciones: (versión destino, script). El estado se guarda
# en ``PRAGMA user_version``; solo se aplican las pendientes, en orden.
MIGRACIONES: list[tuple[int, str]] = [
    (1, ESQUEMA_V1),
    (2, MIGRACION_V2),
]

VERSION_ESQUEMA = MIGRACIONES[-1][0]


def ruta_db() -> str:
    """Ruta del archivo SQLite, resuelta en cada llamada.

    Se lee el entorno cada vez para que las pruebas puedan aislar la base de
    datos con ``monkeypatch.setenv``.
    """
    return os.environ.get("PARQUEADERO_DB", DB_POR_DEFECTO)


def _conectar() -> sqlite3.Connection:
    conexion = sqlite3.connect(ruta_db())
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    # Espera a que se libere el bloqueo de escritura en vez de fallar de
    # inmediato; imprescindible bajo peticiones concurrentes.
    conexion.execute("PRAGMA busy_timeout = 5000")
    return conexion


def _aplicar_migraciones(conexion: sqlite3.Connection) -> None:
    """Aplica, en orden, las migraciones pendientes según ``user_version``."""
    version = conexion.execute("PRAGMA user_version").fetchone()[0]
    for numero, script in MIGRACIONES:
        if numero <= version:
            continue
        conexion.executescript(script)
        conexion.execute(f"PRAGMA user_version = {int(numero)}")


def inicializar() -> None:
    """Aplica el esquema y siembra tarifas por defecto si no existen."""
    with _conectar() as conexion:
        _aplicar_migraciones(conexion)
        existentes = conexion.execute("SELECT COUNT(*) FROM tarifas").fetchone()[0]
        if existentes == 0:
            conexion.executemany(
                "INSERT INTO tarifas (tipo_vehiculo, valor_hora_centavos, fraccion_minutos) "
                "VALUES (?, ?, ?)",
                [("auto", 500000, 60), ("moto", 300000, 60), ("camioneta", 700000, 60)],
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
