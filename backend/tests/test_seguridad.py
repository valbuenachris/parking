"""Pruebas de autenticación, CORS, cabeceras de seguridad y límite de tasa."""

from __future__ import annotations

from conftest import TOKEN_PRUEBA

from app import limites
from app.main import valor_hsts


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


def test_token_corto_falla_cerrado(cliente_token_corto):
    assert cliente_token_corto.get("/api/tarifas").status_code == 503


def test_hsts_solo_sobre_https(cliente, cliente_https):
    assert "strict-transport-security" not in cliente.get("/api/salud").headers
    assert "strict-transport-security" in cliente_https.get("/api/salud").headers


def test_cabeceras_de_seguridad(cliente):
    respuesta = cliente.get("/api/salud")
    assert respuesta.headers["x-content-type-options"] == "nosniff"
    assert respuesta.headers["x-frame-options"] == "DENY"
    assert respuesta.headers["referrer-policy"] == "no-referrer"
    assert "content-security-policy" in respuesta.headers


def test_cors_permite_origen_configurado(cliente):
    respuesta = cliente.get("/api/salud", headers={"Origin": "https://localhost"})
    assert respuesta.headers.get("access-control-allow-origin") == "https://localhost"


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


def test_xff_forjado_no_burla_el_limite(cliente, monkeypatch):
    """Una X-Forwarded-For inventada no cambia la clave del limitador.

    El peer TCP del cliente de pruebas no está en la subred de confianza, así
    que la cabecera se ignora y las tres peticiones comparten la misma clave.
    """
    monkeypatch.setenv("PARQUEADERO_RATE_LIMIT", "2/60")
    limites.reiniciar()
    for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        respuesta = cliente.get("/api/salud", headers={"X-Forwarded-For": ip})
        assert respuesta.status_code == (200 if ip != "10.0.0.3" else 429)


def test_tope_de_limites_recorta_configuracion(monkeypatch):
    monkeypatch.setenv("PARQUEADERO_RATE_LIMIT", "1000000/1000000")
    assert limites.configuracion() == (limites.MAXIMO_TOPE, limites.VENTANA_TOPE)
    monkeypatch.setenv("PARQUEADERO_RATE_LIMIT", "basura")
    assert limites.configuracion() == (120, 60)


def test_hsts_por_defecto_corto_en_desarrollo(monkeypatch):
    monkeypatch.delenv("PARQUEADERO_HSTS", raising=False)
    monkeypatch.delenv("PARQUEADERO_ENTORNO", raising=False)
    assert valor_hsts() == "max-age=300"


def test_hsts_largo_en_produccion(monkeypatch):
    monkeypatch.delenv("PARQUEADERO_HSTS", raising=False)
    monkeypatch.setenv("PARQUEADERO_ENTORNO", "produccion")
    assert valor_hsts() == "max-age=31536000; includeSubDomains"


def test_hsts_configurable_en_respuesta(cliente_https_hsts):
    respuesta = cliente_https_hsts.get("/api/salud")
    assert respuesta.headers["strict-transport-security"] == "max-age=123"
