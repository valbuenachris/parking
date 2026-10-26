"""Pruebas de las reglas de negocio y de los endpoints principales.

Cada prueba de API recibe un cliente con una base de datos SQLite aislada
(fixture ``cliente`` en ``conftest.py``).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.database import conexion, inicializar
from app.models import Tarifa
from app.services import (
    ahora_iso,
    calcular_total,
    centavos_a_decimal,
    decimal_a_centavos,
    minutos_transcurridos,
    normalizar_iso,
    parsear_fecha,
)


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _rango(minutos: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutos)).replace(microsecond=0).isoformat()


# --- Reglas de negocio (unitarias) ---------------------------------------


def test_minutos_transcurridos():
    entrada = "2026-01-01T10:00:00+00:00"
    salida = "2026-01-01T11:30:00+00:00"
    assert minutos_transcurridos(entrada, salida) == 90


def test_normaliza_fechas_a_utc():
    assert normalizar_iso("2026-01-01T12:00:00-05:00") == "2026-01-01T17:00:00+00:00"
    assert normalizar_iso("2026-01-01T17:00:00Z") == "2026-01-01T17:00:00+00:00"


def test_rechaza_fechas_sin_zona_o_invalidas():
    with pytest.raises(ValueError):
        parsear_fecha("2026-01-01T10:00:00")
    with pytest.raises(ValueError):
        parsear_fecha("no-es-fecha")


def test_calcular_total_por_fraccion_exacto():
    tarifa = Tarifa(tipo_vehiculo="auto", valor_hora=Decimal("6000"), fraccion_minutos=30)
    assert calcular_total(0, tarifa) == Decimal("3000.00")
    assert calcular_total(30, tarifa) == Decimal("3000.00")
    assert calcular_total(31, tarifa) == Decimal("6000.00")


# --- Endpoints (con base de datos aislada) --------------------------------


def test_flujo_ingreso_y_salida(cliente):
    ingreso = cliente.post("/api/tickets/ingresos", json={"placa": "abc123", "tipo_vehiculo": "auto"})
    assert ingreso.status_code == 201
    ticket = ingreso.json()
    assert ticket["placa"] == "ABC123"
    assert ticket["hora_salida"] is None
    assert ticket["hora_entrada"].endswith("+00:00")

    salida = cliente.post(f"/api/tickets/{ticket['id']}/salida")
    assert salida.status_code == 200
    cuerpo = salida.json()
    assert cuerpo["factura"]["placa"] == "ABC123"
    assert cuerpo["factura"]["total"] > 0

    facturas = cliente.get("/api/facturas")
    assert facturas.status_code == 200
    assert any(f["placa"] == "ABC123" for f in facturas.json())


def test_no_permite_doble_ingreso(cliente):
    cliente.post("/api/tickets/ingresos", json={"placa": "XYZ789", "tipo_vehiculo": "moto"})
    repetido = cliente.post("/api/tickets/ingresos", json={"placa": "XYZ789", "tipo_vehiculo": "moto"})
    assert repetido.status_code == 409


def test_no_permite_doble_cierre(cliente):
    ingreso = cliente.post("/api/tickets/ingresos", json={"placa": "DUP001", "tipo_vehiculo": "auto"})
    ticket_id = ingreso.json()["id"]

    primera = cliente.post(f"/api/tickets/{ticket_id}/salida")
    assert primera.status_code == 200

    segunda = cliente.post(f"/api/tickets/{ticket_id}/salida")
    assert segunda.status_code == 409
    assert segunda.json()["detail"] == "El ticket ya fue cerrado"


def test_totales_exactos_en_resumen(cliente):
    cliente.put("/api/tarifas/auto", json={"tipo_vehiculo": "auto", "valor_hora": 6000, "fraccion_minutos": 30})
    ingreso = cliente.post("/api/tickets/ingresos", json={"placa": "EXA001", "tipo_vehiculo": "auto"})
    ticket_id = ingreso.json()["id"]
    salida = cliente.post(f"/api/tickets/{ticket_id}/salida")
    assert salida.json()["factura"]["total"] == "3000.00"

    respuesta = cliente.get(
        "/api/informes/resumen",
        params={"desde": _rango(-60), "hasta": _rango(60)},
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["tickets_cerrados"] == 1
    assert cuerpo["facturado_total"] == "3000.00"
    assert cuerpo["por_tipo"] == {"auto": "3000.00"}


def test_filtros_de_facturas_respetan_zona_horaria(cliente):
    ingreso = cliente.post("/api/tickets/ingresos", json={"placa": "TZ0001", "tipo_vehiculo": "auto"})
    cliente.post(f"/api/tickets/{ingreso.json()['id']}/salida")

    dentro = cliente.get("/api/facturas", params={"desde": _rango(-60), "hasta": _rango(60)})
    assert dentro.status_code == 200
    assert len(dentro.json()) == 1

    fuera = cliente.get("/api/facturas", params={"desde": _rango(60), "hasta": _rango(120)})
    assert fuera.status_code == 200
    assert fuera.json() == []


def test_validaciones_de_entrada(cliente):
    corta = cliente.post("/api/tickets/ingresos", json={"placa": "A", "tipo_vehiculo": "auto"})
    assert corta.status_code == 422

    tipo_invalido = cliente.post("/api/tickets/ingresos", json={"placa": "ABC123", "tipo_vehiculo": "barco"})
    assert tipo_invalido.status_code == 422

    tarifa_invalida = cliente.put(
        "/api/tarifas/auto", json={"tipo_vehiculo": "auto", "valor_hora": 0, "fraccion_minutos": 60}
    )
    assert tarifa_invalida.status_code == 422


def test_validaciones_de_fechas(cliente):
    sin_zona = cliente.get(
        "/api/informes/resumen",
        params={"desde": "2026-01-01T00:00:00", "hasta": "2026-01-02T00:00:00"},
    )
    assert sin_zona.status_code == 422

    malformada = cliente.get("/api/facturas", params={"desde": "ayer"})
    assert malformada.status_code == 422

    invertida = cliente.get(
        "/api/informes/resumen",
        params={"desde": _rango(60), "hasta": _rango(-60)},
    )
    assert invertida.status_code == 400


def test_tarifa_con_tipo_que_no_coincide(cliente):
    respuesta = cliente.put(
        "/api/tarifas/auto",
        json={"tipo_vehiculo": "moto", "valor_hora": 3000, "fraccion_minutos": 60},
    )
    assert respuesta.status_code == 400


# --- Integridad de montos y esquema ---------------------------------------


def test_round_trip_decimal_a_centavos_y_vuelta():
    for valor in ("0.00", "0.01", "3000.00", "1234.56", "99999999.99"):
        monto = Decimal(valor)
        assert centavos_a_decimal(decimal_a_centavos(monto)) == monto


def test_montos_se_serializan_como_cadena(cliente):
    ingreso = cliente.post("/api/tickets/ingresos", json={"placa": "STR001", "tipo_vehiculo": "auto"})
    salida = cliente.post(f"/api/tickets/{ingreso.json()['id']}/salida")
    cuerpo = salida.json()
    assert isinstance(cuerpo["factura"]["total"], str)
    assert isinstance(cuerpo["factura"]["valor_hora"], str)
    assert cuerpo["ticket"]["valor_cobrado"] == cuerpo["factura"]["total"]


def test_check_rechaza_monto_negativo(tmp_path, monkeypatch):
    monkeypatch.setenv("PARQUEADERO_DB", str(tmp_path / "check.db"))
    inicializar()
    with pytest.raises(sqlite3.IntegrityError):
        with conexion() as db:
            db.execute(
                "INSERT INTO tarifas (tipo_vehiculo, valor_hora_centavos, fraccion_minutos) "
                "VALUES ('prueba', -1, 60)"
            )


def test_concurrencia_doble_ingreso_crea_un_solo_ticket(tmp_path, monkeypatch):
    monkeypatch.setenv("PARQUEADERO_DB", str(tmp_path / "carrera.db"))
    inicializar()
    barrera = threading.Barrier(2)
    resultados: list[str] = []
    candado = threading.Lock()

    def intentar() -> None:
        barrera.wait()
        try:
            with conexion() as db:
                db.execute(
                    "INSERT INTO tickets (placa, tipo_vehiculo, hora_entrada) VALUES (?, ?, ?)",
                    ("CARRERA1", "auto", ahora_iso()),
                )
            resultado = "creado"
        except sqlite3.IntegrityError:
            resultado = "conflicto"
        with candado:
            resultados.append(resultado)

    hilos = [threading.Thread(target=intentar) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(resultados) == ["conflicto", "creado"]
    with conexion() as db:
        abiertos = db.execute(
            "SELECT COUNT(*) FROM tickets WHERE placa = ? AND hora_salida IS NULL",
            ("CARRERA1",),
        ).fetchone()[0]
    assert abiertos == 1


def test_migracion_conserva_datos_y_aplica_strict(tmp_path, monkeypatch):
    from app.database import ESQUEMA_V1, VERSION_ESQUEMA

    ruta = tmp_path / "legacy.db"
    monkeypatch.setenv("PARQUEADERO_DB", str(ruta))
    cruda = sqlite3.connect(ruta)
    try:
        cruda.executescript(ESQUEMA_V1)
        cruda.execute("PRAGMA user_version = 1")
        cruda.execute(
            "INSERT INTO tarifas (tipo_vehiculo, valor_hora_centavos, fraccion_minutos) "
            "VALUES ('auto', 500000, 60)"
        )
        cruda.commit()
    finally:
        cruda.close()

    inicializar()

    with conexion() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == VERSION_ESQUEMA
        indice = db.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' AND name = 'tickets_abiertos_por_placa'"
        ).fetchone()
        assert indice is not None
        assert db.execute("SELECT COUNT(*) FROM tarifas").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO tarifas (tipo_vehiculo, valor_hora_centavos, fraccion_minutos) "
                "VALUES ('moto', 'no-es-entero', 60)"
            )
