"""Autenticación por token compartido para el panel.

La API del panel se protege con un token secreto definido en la variable de
entorno ``PARQUEADERO_TOKEN``. El cliente puede enviarlo como
``Authorization: Bearer <token>`` o como cabecera ``X-API-Key: <token>``.

Si no se configura el token, la API **falla cerrada**: responde 503 en los
endpoints protegidos en lugar de dejarlos abiertos.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException

ESQUEMA = "Bearer"

# Longitud mínima exigida al token. Un token corto es trivial de adivinar por
# fuerza bruta, así que se trata como "no configurado" y la API falla cerrada.
LONGITUD_MINIMA_TOKEN = 32


def token_configurado() -> str:
    """Token esperado según el entorno (cadena vacía si falta o es muy corto)."""
    token = os.environ.get("PARQUEADERO_TOKEN", "").strip()
    if len(token) < LONGITUD_MINIMA_TOKEN:
        return ""
    return token


def _token_presentado(authorization: str | None, x_api_key: str | None) -> str | None:
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    if authorization:
        partes = authorization.split(None, 1)
        if len(partes) == 2 and partes[0].lower() == ESQUEMA.lower():
            return partes[1].strip()
    return None


def requiere_token(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Dependencia de FastAPI que exige un token válido."""
    esperado = token_configurado()
    if not esperado:
        raise HTTPException(
            status_code=503,
            detail=(
                "Autenticación no configurada: define PARQUEADERO_TOKEN "
                f"con al menos {LONGITUD_MINIMA_TOKEN} caracteres"
            ),
        )
    presentado = _token_presentado(authorization, x_api_key)
    if not presentado or not hmac.compare_digest(presentado.encode(), esperado.encode()):
        raise HTTPException(
            status_code=401,
            detail="Token inválido o ausente",
            headers={"WWW-Authenticate": ESQUEMA},
        )
