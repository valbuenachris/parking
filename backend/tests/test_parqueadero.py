"""Pruebas de las reglas de negocio y de los endpoints principales."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models import Tarifa
from app.services import calcular_total, minutos_transcurridos

cliente = TestClient(app)


def test_minutos_transcurridos():
    entrada = "2026-01-01T10:00:00"
    salida = "2026-01-01T11:30:00"
    assert minutos_transcurridos(entrada, salida) == 90


def test_calcular_total_por_fraccion():
    tarifa = Tarifa(tipo_vehiculo="auto", valor_hora=6000.0, fraccion_minutos=30)
    assert calcular_total(30, tarifa) == 3000.0
    assert calcular_total(31, tarifa) == 6000.0


def test_flujo_ingreso_y_salida():
    ingreso = cliente.post("/api/tickets/ingresos", json={"placa": "ABC123", "tipo_vehiculo": "auto"})
    assert ingreso.status_code == 201
    ticket = ingreso.json()
    assert ticket["hora_salida"] is None

    salida = cliente.post(f"/api/tickets/{ticket['id']}/salida")
    assert salida.status_code == 200
    cuerpo = salida.json()
    assert cuerpo["factura"]["placa"] == "ABC123"
    assert cuerpo["factura"]["total"] >= 0

    facturas = cliente.get("/api/facturas")
    assert facturas.status_code == 200
    assert any(f["placa"] == "ABC123" for f in facturas.json())


def test_no_permite_doble_ingreso():
    cliente.post("/api/tickets/ingresos", json={"placa": "XYZ789", "tipo_vehiculo": "moto"})
    repetido = cliente.post("/api/tickets/ingresos", json={"placa": "XYZ789", "tipo_vehiculo": "moto"})
    assert repetido.status_code == 409


def test_resumen():
    desde = (datetime.now() - timedelta(days=1)).replace(microsecond=0).isoformat()
    hasta = (datetime.now() + timedelta(days=1)).replace(microsecond=0).isoformat()
    respuesta = cliente.get("/api/informes/resumen", params={"desde": desde, "hasta": hasta})
    assert respuesta.status_code == 200
    assert "facturado_total" in respuesta.json()
