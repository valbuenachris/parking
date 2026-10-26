"""Configuración común de las pruebas.

Cada prueba obtiene una base de datos SQLite aislada en un directorio temporal,
de modo que no comparte estado ni depende del orden de ejecución.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.database import inicializar  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("PARQUEADERO_DB", str(tmp_path / "parqueadero_test.db"))
    inicializar()
    with TestClient(app) as test_client:
        yield test_client
