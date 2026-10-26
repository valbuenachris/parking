"""Configuración común de las pruebas.

Cada prueba obtiene una base de datos SQLite aislada en un directorio temporal,
de modo que no comparte estado ni depende del orden de ejecución. La API se
protege con un token de prueba y un límite de tasa holgado.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app import limites  # noqa: E402
from app.database import inicializar  # noqa: E402
from app.main import app  # noqa: E402

TOKEN_PRUEBA = "token-de-prueba-con-longitud-suficiente-01"


@contextmanager
def _cliente(
    tmp_path,
    monkeypatch,
    *,
    con_token: bool,
    token: str = TOKEN_PRUEBA,
    rate_limit: str = "1000/60",
    base_url: str | None = None,
):
    monkeypatch.setenv("PARQUEADERO_DB", str(tmp_path / "parqueadero_test.db"))
    monkeypatch.setenv("PARQUEADERO_TOKEN", token)
    monkeypatch.setenv("PARQUEADERO_RATE_LIMIT", rate_limit)
    limites.reiniciar()
    inicializar()
    cliente = TestClient(app) if base_url is None else TestClient(app, base_url=base_url)
    with cliente as test_client:
        if con_token:
            test_client.headers.update({"X-API-Key": TOKEN_PRUEBA})
        yield test_client


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    """Cliente autenticado con el token de prueba."""
    with _cliente(tmp_path, monkeypatch, con_token=True) as test_client:
        yield test_client


@pytest.fixture()
def cliente_sin_token(tmp_path, monkeypatch):
    """Cliente sin cabecera de autenticación (el token sí está configurado)."""
    with _cliente(tmp_path, monkeypatch, con_token=False) as test_client:
        yield test_client


@pytest.fixture()
def cliente_sin_configurar(tmp_path, monkeypatch):
    """Cliente cuando PARQUEADERO_TOKEN no está definido."""
    with _cliente(tmp_path, monkeypatch, con_token=False, token="") as test_client:
        yield test_client


@pytest.fixture()
def cliente_token_corto(tmp_path, monkeypatch):
    """Cliente cuando PARQUEADERO_TOKEN es más corto que el mínimo exigido."""
    with _cliente(tmp_path, monkeypatch, con_token=True, token="corto") as test_client:
        yield test_client


@pytest.fixture()
def cliente_https(tmp_path, monkeypatch):
    """Cliente que simula que la app termina el TLS (esquema https)."""
    with _cliente(
        tmp_path, monkeypatch, con_token=True, base_url="https://testserver"
    ) as test_client:
        yield test_client
