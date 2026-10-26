#!/bin/sh
# Genera un certificado autofirmado de desarrollo al arrancar el contenedor si
# no existe ya en el volumen de certificados. Así la clave privada no queda
# horneada en la imagen.
#
# En producción (PARQUEADERO_ENTORNO=produccion) NO se genera un autofirmado: si
# falta el certificado se falla, para no servir TLS con un certificado de
# mentira. En su lugar monta un certificado real (fullchain.pem + privkey.pem).
set -e

CERT_DIR="${CERT_DIR:-/etc/nginx/certs}"
CERT_PUB="$CERT_DIR/fullchain.pem"
CERT_KEY="$CERT_DIR/privkey.pem"

if [ -s "$CERT_PUB" ] && [ -s "$CERT_KEY" ]; then
    exit 0
fi

ENTORNO=$(printf '%s' "${PARQUEADERO_ENTORNO:-desarrollo}" | tr '[:upper:]' '[:lower:]')
case "$ENTORNO" in
    produccion|production)
        echo "ERROR: no hay certificado TLS en $CERT_DIR y PARQUEADERO_ENTORNO=$ENTORNO." >&2
        echo "En producción monta fullchain.pem y privkey.pem reales; no se genera un autofirmado." >&2
        exit 1
        ;;
esac

echo "Generando certificado autofirmado de desarrollo en $CERT_DIR"
mkdir -p "$CERT_DIR"
# SAN con los nombres que usan el navegador y el CI (localhost y loopback). Se
# pueden añadir más nombres con PARQUEADERO_CERT_SAN (p. ej. "DNS:parqueadero").
SAN="DNS:localhost,IP:127.0.0.1,IP:::1"
if [ -n "${PARQUEADERO_CERT_SAN:-}" ]; then
    SAN="$SAN,$PARQUEADERO_CERT_SAN"
fi
openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout "$CERT_KEY" \
    -out "$CERT_PUB" \
    -subj "/CN=localhost" \
    -addext "subjectAltName=$SAN"
