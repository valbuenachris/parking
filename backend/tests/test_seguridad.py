"""Pruebas de autenticación, CORS, cabeceras de seguridad y límite de tasa."""

from __future__ import annotations

from conftest import TOKEN_PRUEBA

from app import limites


def test_salud_es_publica(cliente_sin_token):
    assert cliente_sin_token.get("/api/salud").status_code == 200


def test_endpoints_del_panel_exigen_token(cliente_sin_token):
    assert cliente_sin_token.get("/api/tarifas").status_code == 401
    assert cliente_sin_token.get("/api/tickets/activos").status_code == 401
    ingreso = cliente_sin_token.post(
        "/api/tickets/ingresos", json={"placa": "SEC001", "tipo_vehiculo": "auto"}
    )
    assert ingreso.status_code == 401


def test_token_incorrecto_es_rechazado(cliente_sin_token):
    respuesta = cliente_sin_token.get("/api/tarifas", headers={"X-API-Key": "incorrecto"})
    assert respuesta.status_code == 401
    assert respuesta.headers.get("www-authenticate") == "Bearer"


def test_token_valido_por_cabecera_bearer(cliente_sin_token):
    respuesta = cliente_sin_token.get(
        "/api/tarifas", headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"}
    )
    assert respuesta.status_code == 200


def test_token_valido_por_x_api_key(cliente):
    assert cliente.get("/api/tarifas").status_code == 200


def test_sin_token_configurado_falla_cerrado(cliente_sin_configurar):
    assert cliente_sin_configurar.get("/api/tarifas").status_code == 503


def test_cabeceras_de_seguridad(cliente):
    respuesta = cliente.get("/api/salud")
    assert respuesta.headers["x-content-type-options"] == "nosniff"
    assert respuesta.headers["x-frame-options"] == "DENY"
    assert respuesta.headers["referrer-policy"] == "no-referrer"
    assert "content-security-policy" in respuesta.headers


def test_cors_permite_origen_configurado(cliente):
    respuesta = cliente.get("/api/salud", headers={"Origin": "http://localhost:8080"})
    assert respuesta.headers.get("access-control-allow-origin") == "http://localhost:8080"


def test_cors_rechaza_origen_desconocido(cliente):
    respuesta = cliente.get("/api/salud", headers={"Origin": "http://malicioso.example"})
    assert "access-control-allow-origin" not in respuesta.headers


def test_limite_de_tasa(cliente, monkeypatch):
    monkeypatch.setenv("PARQUEADERO_RATE_LIMIT", "2/60")
    limites.reiniciar()
    assert cliente.get("/api/salud").status_code == 200
    assert cliente.get("/api/salud").status_code == 200
    excedido = cliente.get("/api/salud")
    assert excedido.status_code == 429
    assert "retry-after" in excedido.headers
