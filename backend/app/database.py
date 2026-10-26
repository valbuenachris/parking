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

# ``STRICT`` requiere SQLite 3.37 o superior. Se comprueba antes de aplicar el
# esquema para fallar con un mensaje claro en vez de con un error críptico.
SQLITE_MINIMA = (3, 37, 0)

# Esquema inicial (versión 1). Se mantiene tal cual para poder migrar bases de
# datos creadas antes de introducir el versionado con PRAGMA user_version.
# ``PRAGMA user_version`` se fija dentro de la misma transacción para que el
# esquema y su versión sean atómicos.
ESQUEMA_V1 = """
BEGIN;
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
PRAGMA user_version = 1;
COMMIT;
"""

# Migración a la versión 2: reconstruye las tablas como STRICT, añade CHECK de
# integridad (montos y tiempos no negativos, tarifas positivas), un índice único
# parcial que impide dos tickets abiertos para la misma placa (comparando sin
# distinguir mayúsculas) y un índice para los filtros por hora de salida.
#
# Antes de crear las restricciones se sanean los datos heredados que no las
# cumplirían: montos negativos y tickets abiertos duplicados por placa. Así la
# migración no falla y deja la base en un estado válido. ``PRAGMA user_version``
# va dentro de la misma transacción para que el esquema y la versión sean
# atómicos.
MIGRACION_V2 = """
PRAGMA foreign_keys = OFF;
BEGIN;
ALTER TABLE tarifas RENAME TO tarifas_antigua;
ALTER TABLE tickets RENAME TO tickets_antigua;
ALTER TABLE facturas RENAME TO facturas_antigua;

-- Saneo previo: valores que violarían los CHECK nuevos.
UPDATE tarifas_antigua SET valor_hora_centavos = 1 WHERE valor_hora_centavos <= 0;
UPDATE tarifas_antigua SET fraccion_minutos = 60
    WHERE fraccion_minutos < 1 OR fraccion_minutos > 1440;
UPDATE tickets_antigua SET valor_cobrado_centavos = NULL
    WHERE valor_cobrado_centavos < 0;
-- Conserva solo el primer ticket abierto por placa (sin distinguir mayúsculas);
-- los duplicados abiertos no pueden tener factura, así que borrarlos es seguro.
DELETE FROM tickets_antigua
    WHERE hora_salida IS NULL
      AND id NOT IN (
          SELECT MIN(id) FROM tickets_antigua
          WHERE hora_salida IS NULL GROUP BY placa COLLATE NOCASE
      );
UPDATE facturas_antigua SET minutos = 0 WHERE minutos < 0;
UPDATE facturas_antigua SET valor_hora_centavos = 0 WHERE valor_hora_centavos < 0;
UPDATE facturas_antigua SET total_centavos = 0 WHERE total_centavos < 0;

CREATE TABLE tarifas (
    tipo_vehiculo TEXT PRIMARY KEY,
    valor_hora_centavos INTEGER NOT NULL CHECK (valor_hora_centavos > 0),
    fraccion_minutos INTEGER NOT NULL DEFAULT 60
        CHECK (fraccion_minutos BETWEEN 1 AND 1440)
) STRICT;

CREATE TABLE tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    placa TEXT NOT NULL COLLATE NOCASE,
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

CREATE INDEX IF NOT EXISTS facturas_hora_salida ON facturas (hora_salida);

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
PRAGMA user_version = 2;
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


def _verificar_sqlite() -> None:
    """Falla con un mensaje claro si SQLite es anterior a 3.37 (STRICT)."""
    if sqlite3.sqlite_version_info < SQLITE_MINIMA:
        raise RuntimeError(
            "Se requiere SQLite {}.{}.{} o superior (tablas STRICT); "
            "la versión instalada es {}.".format(*SQLITE_MINIMA, sqlite3.sqlite_version)
        )


def _conectar() -> sqlite3.Connection:
    conexion = sqlite3.connect(ruta_db())
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    # Espera a que se libere el bloqueo de escritura en vez de fallar de
    # inmediato; imprescindible bajo peticiones concurrentes.
    conexion.execute("PRAGMA busy_timeout = 5000")
    # WAL permite lecturas mientras hay una escritura en curso. Puede no estar
    # disponible en algunos sistemas de archivos (p. ej. redes), así que un
    # fallo no debe impedir arrancar.
    try:
        conexion.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    return conexion


def _aplicar_migraciones(conexion: sqlite3.Connection) -> None:
    """Aplica, en orden, las migraciones pendientes según ``user_version``.

    Cada script fija ``PRAGMA user_version`` dentro de su propia transacción, de
    modo que el esquema y la versión quedan siempre consistentes.
    """
    for numero, script in MIGRACIONES:
        version = conexion.execute("PRAGMA user_version").fetchone()[0]
        if numero <= version:
            continue
        conexion.executescript(script)


def inicializar() -> None:
    """Aplica el esquema y siembra tarifas por defecto si no existen."""
    _verificar_sqlite()
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
